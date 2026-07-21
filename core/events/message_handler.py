import asyncio
import base64
import io
import math
import json
import re
import discord
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from utils.logger import setup_logging
from utils.wellness import get_wellness_reminder, should_give_reminder
from utils.identity import resolve_name, clean_name, build_user_context
from tools.file_reading import build_attachment_context
import tools.qwen_batch as qwen_batch
from config import COOLDOWN_REPLY_DELAY, VLM_MONITOR_CHANNEL_ID, VLM_MAX_IMAGES, VLM_MAX_IMAGE_SIZE
from core.module_manager import module_manager

logger = setup_logging()
WIB = ZoneInfo("Asia/Jakarta")

class MessageHandler:
    def __init__(self, bot, ai_service, cooldown_manager, micro_rag,
                 web_rate_limiter=None):
        self.bot = bot
        self.ai = ai_service
        self.cooldown = cooldown_manager
        self.micro_rag = micro_rag  # Micro-RAG untuk profiling user
        self.web_rate_limiter = web_rate_limiter  # Web scraping rate limiter

    def clean_message(self, content):
        """Bersihkan pesan dari mention bot."""
        return content.replace(f"<@{self.bot.user.id}>", "")\
                      .replace(f"<@!{self.bot.user.id}>", "")\
                      .strip()

    def format_user_identity(self, message: discord.Message) -> tuple[str, str]:
        """
        Format identitas user: nama bersih + role.
        PAKAI resolve_name() dari utils/identity.py — SATU-SATUNYA sumber nama.
        """
        author = message.author
        # Gunakan central resolver — tidak ada lagi "global_name / display_name"
        name = clean_name(resolve_name(message))
        
        role_name = "DM"
        if isinstance(author, discord.Member):
            guild_roles = [role for role in author.roles if role.name != "@everyone"]
            if guild_roles:
                role_name = guild_roles[-1].name
            else:
                role_name = "Member"
        
        return name, role_name

    # ========== HELPER FUNCTIONS (Pisah dari main logic) ==========

    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
    EXT_TO_MIME = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    }

    async def _get_image_parts(self, attachments: list) -> tuple:
        """
        Download image attachments untuk VLM.
        Returns (gemini_parts, raw_images):
          - gemini_parts: list inline_data untuk Gemini API
          - raw_images: list (filename, bytes) untuk monitoring channel
        """
        gemini_parts = []
        raw_images = []
        if not attachments:
            return gemini_parts, raw_images

        count = 0
        for attachment in attachments:
            if count >= VLM_MAX_IMAGES:
                break

            ext = Path(attachment.filename).suffix.lower()
            if ext not in self.IMAGE_EXTENSIONS:
                continue

            if attachment.size > VLM_MAX_IMAGE_SIZE:
                logger.warning(f"[VLM] {attachment.filename} terlalu besar ({attachment.size} bytes), skip")
                continue

            content_type = attachment.content_type or ""
            if not content_type.startswith("image/"):
                content_type = self.EXT_TO_MIME.get(ext, "")
                if not content_type:
                    continue

            try:
                image_bytes = await attachment.read()
                b64 = base64.b64encode(image_bytes).decode("utf-8")
                gemini_parts.append({
                    "inline_data": {
                        "mime_type": content_type,
                        "data": b64,
                    }
                })
                raw_images.append((attachment.filename, image_bytes))
                count += 1
                logger.info(f"[VLM] Image attached: {attachment.filename} ({len(image_bytes)} bytes)")
            except Exception as e:
                logger.warning(f"[VLM] Gagal proses {attachment.filename}: {e}")

        return gemini_parts, raw_images

    async def _forward_to_monitor_channel(
        self,
        original_msg: discord.Message,
        cleaned_text: str,
        reply: str,
        raw_images: list,
    ):
        """Forward VLM request (user message + image + AI response) ke monitoring channel."""
        channel = self.bot.get_channel(VLM_MONITOR_CHANNEL_ID)
        if not channel:
            logger.warning(f"[VLM] Monitoring channel {VLM_MONITOR_CHANNEL_ID} tidak ditemukan")
            return

        try:
            embed = discord.Embed(
                title="📸 VLM Request",
                color=discord.Color.purple(),
                timestamp=original_msg.created_at,
            )
            embed.add_field(name="User", value=f"{original_msg.author.mention} (`{original_msg.author.id}`)", inline=False)
            embed.add_field(name="Channel", value=original_msg.channel.mention, inline=False)
            embed.add_field(name="Message", value=cleaned_text or "*[gambar saja]*", inline=False)
            embed.add_field(name="Response", value=reply[:1500] + "..." if len(reply) > 1500 else reply, inline=False)

            files = [discord.File(io.BytesIO(img_bytes), filename=filename) for filename, img_bytes in raw_images]

            await channel.send(embed=embed, files=files)
            logger.info(f"[VLM] Forwarded to monitoring channel {VLM_MONITOR_CHANNEL_ID}")
        except Exception as e:
            logger.error(f"[VLM] Gagal forward ke monitoring channel: {e}")

    async def _get_attachment_context(self, attachments: list, channel_id: int) -> str:
        """
        Ambil context dari attachment hanya jika channel mengaktifkan fitur ini.
        """
        if not attachments:
            return ""
        
        # Cek jika channel memiliki fitur attachment processing
        if hasattr(qwen_batch, 'is_channel_enabled') and qwen_batch.is_channel_enabled(channel_id):
            return await build_attachment_context(attachments)
        
        return ""

    def _build_gemini_context(
        self,
        user_name: str,
        user_id: int,
        channel_name: str,
        channel_id: int,
        cleaned_message: str,
        timestamp: str,
        server_name: str | None = None,
        server_id: int | None = None,
        attachment_context: str = "",
        rag_context: str = "",
        is_dm: bool = False,
    ) -> str:
        """
        Build structured context untuk AI.
        Nama user sudah di-resolve oleh format_user_identity() via resolve_name().
        HANYA SATU NAMA yang dimasukkan ke context.
        """
        context_type = "dm" if is_dm else "server"
        
        context = (
            f"Nama user: {user_name}\n"
            f"Context: {context_type}\n"
            f"User ID: {user_id}\n"
            f"Channel: {channel_name}\n"
            f"Channel ID: {channel_id}\n"
            f"Timestamp: {timestamp}\n"
            f"Message: {cleaned_message}"
        )
        if server_name:
            context += f"\nServer: {server_name}"
        if server_id:
            context += f"\nServer ID: {server_id}"
        
        if attachment_context:
            context += f"\n\n[Attachment Context]\n{attachment_context}"
        
        if rag_context:
            context += f"\n{rag_context}"
        
        # Constraint ketat: satu nama saja
        context += (
            "\n\nGunakan nama ini saja."
            "\nJangan gunakan nama lain atau variasi."
            "\nJangan gunakan dua nama sekaligus."
            "\nGunakan hanya satu nama user dan jangan mengulang atau menggabungkannya."
        )
        return context

    async def _save_to_history(
        self,
        user_name: str,
        user_id: int,
        channel_name: str,
        channel_id: int,
        message: str,
        response: str,
        timestamp: str
    ) -> None:
        """
        Simpan ke history.json dengan format yang benar.
        PERBAIKAN: Sesuai dengan requirements format.
        
        Format:
        {
            "timestamp": "ISO format",
            "user": "name | id",
            "channel": "name | id",
            "message": "pesan user",
            "response": "respon bot",
            "response_timestamp": "ISO format"
        }
        """
        try:
            # Gunakan file terpisah khusus untuk chat log (Micro-RAG)
            # Jangan campur dengan history.json milik memory.py (format Gemini)
            history_path = Path("data/chat_log.json")
            history_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Load existing data
            if history_path.exists():
                with open(history_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            else:
                data = []
            
            # Create entry dengan format yang benar
            entry = {
                "timestamp": timestamp,
                "user": f"{user_name} | {user_id}",
                "channel": f"{channel_name} | {channel_id}",
                "message": message,
                "response": response,
                "response_timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Append entry
            data.append(entry)
            
            # Trim ke N entri terbaru agar file tidak tumbuh selamanya
            MAX_CHAT_LOG_ENTRIES = 500
            if len(data) > MAX_CHAT_LOG_ENTRIES:
                data = data[-MAX_CHAT_LOG_ENTRIES:]
            
            # Save dengan format yang rapi
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[History] Saved: {user_name} in {channel_name}")
            
        except Exception as e:
            logger.exception("Gagal save history: %s", e)

    # ========== MAIN HANDLER ==========

    async def handle(self, message: discord.Message):
        if message.author.bot:
            return

        try:
            # STEP 1: Extract basic info
            cleaned = self.clean_message(message.content)
            user_name, role_name = self.format_user_identity(message)
            user_id = message.author.id
            channel_id = message.channel.id
            channel_name = getattr(message.channel, "name", "DM")
            server_name = message.guild.name if message.guild else None
            server_id = message.guild.id if message.guild else None
            
            # STEP 1.5: Reset history jika context berubah (server ↔ DM)
            from memory import reset_on_context_change
            reset_on_context_change(guild_id=server_id, user_id=user_id)

            # STEP 2: Get attachment context (hanya untuk channel yang diaktifkan)
            attachment_context = await self._get_attachment_context(message.attachments, channel_id)
            
            # STEP 3: Collect message untuk qwen jika diperlukan
            if hasattr(qwen_batch, 'collect_message'):
                await qwen_batch.collect_message(
                    user_id, user_name, cleaned, channel_id,
                    channel_name=channel_name,
                    server_name=server_name,
                    server_id=server_id,
                    attachment_context=attachment_context,
                    timestamp=message.created_at,
                )

            # STEP 4: Check if bot should reply (mention, reply, atau URL)
            should_reply = False
            has_url = bool(re.search(r'https?://[^\s<>"\']+', cleaned))
            
            if self.bot.user.mentioned_in(message):
                should_reply = True
            if message.reference:
                try:
                    ref = await message.channel.fetch_message(message.reference.message_id)
                    if ref.author == self.bot.user:
                        should_reply = True
                except Exception:
                    pass

            if not should_reply:
                return

            # STEP 4.5: Cek rate limit web scraper (1x per-user per minggu)
            if has_url and self.web_rate_limiter is not None:
                if module_manager.is_enabled("web_scraper"):
                    if not self.web_rate_limiter.can_scrape(user_id):
                        sisa_hari = self.web_rate_limiter.get_remaining_days(user_id)
                        msg = await message.reply(
                            f"⚠️ Maaf {user_name}, fitur web search cuma bisa 1x seminggu per orang. "
                            f"Kamu bisa pakai lagi dalam {sisa_hari} hari. "
                            f"Minta tolong teman yang lain untuk bantu cek link-nya ya! 🙏"
                        )
                        # Tetap lanjut ke Gemini — Gemini bisa jawab tanpa scrap
                        # Tandai bahwa web sudah dicegah (tidak di-mark scraped)
                        self.cooldown.mark_replied(channel_id)
                        return

            # STEP 5: Check cooldown (hanya cek, tanpa update state)
            can_proceed, wait_time = await self.cooldown.check(channel_id)
            if not can_proceed:
                msg = await message.reply(
                    f"⚠️ Tenang dulu ya... Aku lagi istirahat sebentar. "
                    f"Coba lagi dalam {math.ceil(wait_time)} detik."
                )
                asyncio.create_task(self._delete_after_delay(msg))
                return

            # STEP 6: Generate reply dengan context yang benar
            reply = ""
            async with message.channel.typing():
                # Build user message untuk history
                user_msg = (
                    f"{user_name} ({role_name}) | ID: {user_id}\n"
                    f"Channel: {channel_name} (ID: {channel_id})\n"
                    f"Server: {server_name or 'DM'} (ID: {server_id or 'N/A'})\n"
                    f"Timestamp: {message.created_at.isoformat()}\n"
                    f"Message: {cleaned}"
                )
                if attachment_context:
                    user_msg += f"\n\n[Attachments Context]\n{attachment_context}"
                
                # VLM: deteksi image attachments dan kirim sebagai inline_data ke Gemini
                gemini_image_parts, raw_images = await self._get_image_parts(message.attachments)
                if gemini_image_parts:
                    parts = [{"text": user_msg}] + gemini_image_parts
                    await self.ai.add_to_history_parts("user", parts)
                else:
                    await self.ai.add_to_history("user", user_msg)
                history = self.ai.get_history()
                
                # Ambil konteks Micro-RAG (profil user jangka panjang)
                rag_context = self.micro_rag.get_user_context(user_id)
                
                # Build context untuk AI
                is_dm = message.guild is None
                user_context = self._build_gemini_context(
                    user_name=user_name,
                    user_id=user_id,
                    channel_name=channel_name,
                    channel_id=channel_id,
                    cleaned_message=cleaned,
                    timestamp=message.created_at.isoformat(),
                    server_name=server_name,
                    server_id=server_id,
                    attachment_context=attachment_context,
                    rag_context=rag_context,
                    is_dm=is_dm,
                )
                
                # Generate reply dari Gemini
                reply = await self.ai.generate_reply(history, user_context=user_context)

                # STEP 6.5: Catat web scraping sukses (setelah Gemini reply)
                if has_url and self.web_rate_limiter is not None:
                    if module_manager.is_enabled("web_scraper"):
                        from ai.web_scraper import BrowserlessClient
                        scraper = BrowserlessClient()
                        if scraper.enabled and self.web_rate_limiter.can_scrape(user_id):
                            self.web_rate_limiter.mark_scraped(user_id)
                
                # Tambahkan wellness hanya bila belum ada dalam balasan
                # Cek apakah wellness diaktifkan di module manager
                if should_give_reminder() and module_manager.is_enabled("wellness"):
                    wellness = get_wellness_reminder()
                    # Cek apakah wellness sudah ada (case‑insensitive) untuk menghindari duplikasi
                    if wellness and wellness.lower() not in reply.lower():
                        reply = f"{reply}\n\n---\n💡 *Mirai Wellness:* {wellness}"

                await self.ai.add_to_history("assistant", reply)
                
                # Send response ke user (no mention)
                await self._send_long_message(message.channel, reply, reply_to=message)

                # VLM monitor forward: kirim image + reply ke channel monitoring
                if raw_images and VLM_MONITOR_CHANNEL_ID:
                    await self._forward_to_monitor_channel(
                        original_msg=message,
                        cleaned_text=cleaned,
                        reply=reply,
                        raw_images=raw_images,
                    )
            
            # STEP 6.7: Tandai cooldown SETELAH reply sukses dikirim
            self.cooldown.mark_replied(channel_id)
            
            # STEP 7: Save to history.json (PERBAIKAN: format yang benar)
            await self._save_to_history(
                user_name=user_name,
                user_id=user_id,
                channel_name=channel_name,
                channel_id=channel_id,
                message=cleaned,
                response=reply,
                timestamp=message.created_at.isoformat()
            )

        except Exception as e:
            logger.exception("Error in on_message: %s", e)

    async def _delete_after_delay(self, msg: discord.Message, delay_seconds: int = COOLDOWN_REPLY_DELAY):
        await asyncio.sleep(delay_seconds)
        try:
            await msg.delete()
        except Exception:
            pass

    async def _send_long_message(self, destination, content, reply_to=None, limit=2000):
        """Send long message with splitting if needed."""
        if len(content) <= limit:
            if reply_to:
                await reply_to.reply(content)
            else:
                await destination.send(content)
            return
        
        parts = [content[i:i+limit] for i in range(0, len(content), limit)]
        if reply_to:
            await reply_to.reply(parts[0])
            for part in parts[1:]:
                await destination.send(part)
                await asyncio.sleep(0.5)
        else:
            for part in parts:
                await destination.send(part)
                await asyncio.sleep(0.5)
