"""
commands/search_command.py
──────────────────────────
Slash command: /search — pencarian web via Tavily / DuckDuckGo.
Slash command: /search-ai — pencarian web + penjelasan AI dari Mirai.
"""

import sys
import os
from typing import Optional
import discord
from discord import app_commands

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commands.base import BaseCommand
from ai.web_search import WebSearchClient
from ai.gemini import GeminiClient
from ai.query_reformer import query_reformer
from core.module_manager import module_manager
from tools.search_session import search_session_manager
from memory import get_history, add_message, reset_on_context_change
from utils.identity import resolve_name, clean_name, build_user_context
from utils.logger import setup_logging

logger = setup_logging()
web_search = WebSearchClient()
gemini = GeminiClient()


class SearchCommands(BaseCommand):
    def register(self, tree: app_commands.CommandTree):
        # ── /search ─────────────────────────────────────────────────────────
        @tree.command(name="search", description="Cari informasi di web (Tavily / DuckDuckGo)")
        @app_commands.describe(
            query="Apa yang ingin kamu cari?",
            private="Hanya kamu yang bisa lihat hasilnya? (default: False)",
        )
        async def search_command(
            interaction: discord.Interaction,
            query: str,
            private: bool = False,
        ):
            if not module_manager.is_enabled("search"):
                await interaction.response.send_message(
                    "Modul Web Search sedang dinonaktifkan oleh admin.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=private, thinking=True)

            try:
                reformed_query = query_reformer.reformulate(query)
                data = await web_search.search(reformed_query)

                if not data or not data.get("results"):
                    await interaction.followup.send(
                        f"Tidak ada hasil pencarian untuk: **{query}**\n"
                        f"Kemungkinan penyebab: query terlalu spesifik, atau layanan search sedang terganggu.",
                        ephemeral=private,
                    )
                    return

                engine = data.get("engine", "web").capitalize()

                embed = discord.Embed(
                    title=f"Hasil Pencarian: {query}",
                    color=0x3498DB,
                )

                answer = data.get("answer", "")
                if answer:
                    embed.description = f"**Ringkasan:** {answer}"

                for i, r in enumerate(data["results"][:5], 1):
                    title = r.get("title", "Tanpa judul")
                    url = r.get("url", "")
                    content = r.get("content", "")
                    excerpt = content[:200] + "..." if len(content) > 200 else content
                    embed.add_field(
                        name=f"{i}. {title}",
                        value=f"{url}\n{excerpt}" if url else excerpt,
                        inline=False,
                    )

                embed.set_footer(
                    text=f"Diminta oleh {interaction.user.display_name} • Powered by {engine}"
                )

                search_session_manager.create_or_update_session(
                    user_id=interaction.user.id,
                    original_query=query,
                    reformulated_query=reformed_query,
                    results=data.get("results", []),
                    engine=engine.lower(),
                )

                await interaction.followup.send(embed=embed, ephemeral=private)

            except Exception as e:
                logger.exception("[/search] Error: %s", e)
                await interaction.followup.send(
                    f"Terjadi kesalahan saat mencari. Silakan coba lagi nanti.",
                    ephemeral=private,
                )

        # ── /search-ai ──────────────────────────────────────────────────────
        @tree.command(name="search-ai", description="Cari di web lalu minta Mirai jelaskan hasilnya")
        @app_commands.describe(
            query="Apa yang ingin kamu cari dan tanyakan ke Mirai?",
            private="Hanya kamu yang bisa lihat? (default: False)",
        )
        async def search_ai_command(
            interaction: discord.Interaction,
            query: str,
            private: bool = False,
        ):
            if not module_manager.is_enabled("search"):
                await interaction.response.send_message(
                    "Modul Web Search sedang dinonaktifkan oleh admin.", ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=private, thinking=True)

            try:
                user = interaction.user
                guild = interaction.guild
                channel_name = (
                    interaction.channel.name
                    if interaction.channel and hasattr(interaction.channel, "name")
                    else "DM"
                )

                reset_on_context_change(guild_id=guild.id if guild else None, user_id=user.id)
                user_name = clean_name(resolve_name(interaction))

                reformed_query = query_reformer.reformulate(query)

                data = await web_search.search(reformed_query)

                search_context = ""
                if data and data.get("results"):
                    search_context = web_search.format_for_llm(data, reformed_query)
                    search_session_manager.create_or_update_session(
                        user_id=user.id,
                        original_query=query,
                        reformulated_query=reformed_query,
                        results=data.get("results", []),
                        engine=data.get("engine", "web"),
                    )

                prompt = f"Cari informasi tentang: {query}"
                if search_context:
                    prompt = f"Cari informasi tentang: {query}\n\n{search_context}"

                user_context = build_user_context(
                    interaction,
                    extra_info={
                        "Channel": channel_name,
                        "Server": guild.name if guild else "DM",
                        "Pesan": f"Cari informasi tentang: {query}",
                    },
                )

                await add_message("user", prompt)
                history = get_history()
                reply = await gemini.generate(history, user_context=user_context)
                await add_message("assistant", reply)

                if len(reply) > 1900:
                    reply = reply[:1900] + "\n...(pesan dipotong)"

                embed = discord.Embed(description=reply, color=0x00FF88)
                embed.set_author(name=f"Jawaban untuk {user_name}", icon_url=user.display_avatar.url)

                engine_name = data.get("engine", "web").capitalize() if data else "Web"
                embed.set_footer(text=f"Mirai • Web Search + AI • Powered by {engine_name}")
                await interaction.followup.send(embed=embed, ephemeral=private)

            except Exception as e:
                logger.exception("[/search-ai] Error: %s", e)
                await interaction.followup.send(
                    f"Terjadi kesalahan saat mencari. Silakan coba lagi nanti.",
                    ephemeral=private,
                )
