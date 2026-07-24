import discord
from pathlib import Path
from discord import app_commands
from plugins.base import Plugin
from tools.file_reading import build_attachment_context, extract_file_text
from config import SUPPORTED_EXTENSIONS


class FileReaderPlugin(Plugin):
    id = "file_reader"
    name = "File Reader"
    version = "1.0.0"
    author = "Helix"
    description = "Reads and extracts text from uploaded files (PDF, DOCX, XLSX, PPTX, TXT)"
    module_name = "file_reader"
    dependencies = []
    config_defaults = {
        "max_reply_chars": 1900,
    }

    async def on_message(self, message: discord.Message) -> bool:
        if not message.attachments:
            return False
        supported = [
            a for a in message.attachments
            if Path(a.filename).suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        if not supported:
            return False
        return False

    def register_commands(self, tree: app_commands.CommandTree):
        @tree.command(name="readfile", description="Baca teks dari file yang di-attach")
        async def readfile(interaction: discord.Interaction, file: discord.Attachment):
            ext = Path(file.filename).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                await interaction.response.send_message(
                    f"Format `{ext}` tidak didukung. Gunakan: {', '.join(SUPPORTED_EXTENSIONS)}",
                    ephemeral=True,
                )
                return

            raw = await file.read()
            extracted = extract_file_text(file.filename, raw).strip()
            if not extracted:
                await interaction.response.send_message(
                    f"Tidak bisa mengekstrak teks dari `{file.filename}`.",
                    ephemeral=True,
                )
                return

            if len(extracted) > self.get_config("max_reply_chars", 1900):
                extracted = extracted[: self.get_config("max_reply_chars", 1900)]
                extracted += "\n\n... (dipotong)"

            await interaction.response.send_message(
                f"**{file.filename}** ({file.size / 1024:.1f} KB):\n```\n{extracted}\n```"
            )

    @property
    def api(self):
        return {"build_attachment_context": build_attachment_context, "extract_file_text": extract_file_text}
