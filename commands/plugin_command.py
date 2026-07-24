"""
commands/plugin_command.py — Plugin Management Commands

Slash commands untuk mengelola plugin secara runtime:
  /plugin list     — daftar semua plugin
  /plugin load     — load plugin
  /plugin unload   — unload plugin
  /plugin reload   — reload plugin
  /plugin info     — detail plugin
"""

import discord
from discord import app_commands
from commands.base import BaseCommand
from utils.logger import setup_logging

logger = setup_logging()


class PluginCommands(BaseCommand):
    def register(self, tree: app_commands.CommandTree):
        plugin_group = app_commands.Group(
            name="plugin", description="Kelola plugin bot"
        )

        # ── list ─────────────────────────────────────────────────
        @plugin_group.command(name="list", description="Daftar semua plugin")
        async def plugin_list(interaction: discord.Interaction):
            from core.router import _router_cache

            router = _router_cache
            if not router:
                await interaction.response.send_message("❌ Router belum siap.", ephemeral=True)
                return

            pm = router.plugin_manager
            lines = []
            for pid, plugin in pm.plugins.items():
                status = "✅" if plugin.is_enabled() else "⛔"
                lines.append(f"{status} **{plugin.display_name}** v{plugin.version} (`{pid}`)")
            header = f"**📦 Plugin Loaded: {len(lines)}**\n"
            await interaction.response.send_message(header + "\n".join(lines) if lines else "Tidak ada plugin terload.", ephemeral=True)

        # ── load ─────────────────────────────────────────────────
        @plugin_group.command(name="load", description="Load plugin")
        @app_commands.describe(name="Nama/ID plugin")
        @app_commands.default_permissions(administrator=True)
        async def plugin_load(interaction: discord.Interaction, name: str):
            from core.router import _router_cache
            router = _router_cache
            if not router:
                await interaction.response.send_message("❌ Router belum siap.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            plugin = await router.plugin_manager.load_plugin(name)
            if plugin:
                await interaction.followup.send(f"✅ Plugin **{plugin.display_name}** v{plugin.version} berhasil diload.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Gagal load plugin `{name}`. Cek console untuk detail.", ephemeral=True)

        # ── unload ───────────────────────────────────────────────
        @plugin_group.command(name="unload", description="Unload plugin")
        @app_commands.describe(name="Nama/ID plugin")
        @app_commands.default_permissions(administrator=True)
        async def plugin_unload(interaction: discord.Interaction, name: str):
            from core.router import _router_cache
            router = _router_cache
            if not router:
                await interaction.response.send_message("❌ Router belum siap.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            plugin = router.plugin_manager.get_plugin(name)
            if not plugin:
                await interaction.followup.send(f"❌ Plugin `{name}` tidak ditemukan.", ephemeral=True)
                return
            await router.plugin_manager.unload_plugin(name)
            await interaction.followup.send(f"✅ Plugin **{plugin.display_name}** berhasil diunload.", ephemeral=True)

        # ── reload ───────────────────────────────────────────────
        @plugin_group.command(name="reload", description="Reload plugin (unload → load ulang)")
        @app_commands.describe(name="Nama/ID plugin")
        @app_commands.default_permissions(administrator=True)
        async def plugin_reload(interaction: discord.Interaction, name: str):
            from core.router import _router_cache
            router = _router_cache
            if not router:
                await interaction.response.send_message("❌ Router belum siap.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            await router.plugin_manager.unload_plugin(name)
            import importlib
            cls = router.plugin_manager._plugin_classes.get(name)
            if cls:
                mod = importlib.import_module(cls.__module__)
                importlib.reload(mod)
                router.plugin_manager.discover_plugins()
            plugin = await router.plugin_manager.load_plugin(name)
            if plugin:
                router.plugin_manager.register_commands(router.command_group.tree)
                await router.command_group.sync_commands()
                await interaction.followup.send(f"✅ Plugin **{plugin.display_name}** v{plugin.version} berhasil direload.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Gagal reload plugin `{name}`.", ephemeral=True)

        # ── info ─────────────────────────────────────────────────
        @plugin_group.command(name="info", description="Info detail plugin")
        @app_commands.describe(name="Nama/ID plugin")
        async def plugin_info(interaction: discord.Interaction, name: str):
            from core.router import _router_cache
            router = _router_cache
            if not router:
                await interaction.response.send_message("❌ Router belum siap.", ephemeral=True)
                return
            plugin = router.plugin_manager.get_plugin(name)
            if not plugin:
                await interaction.response.send_message(f"❌ Plugin `{name}` tidak ditemukan.", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"📦 {plugin.display_name}",
                description=plugin.description or "Tidak ada deskripsi",
                color=0x00aaff,
            )
            embed.add_field(name="ID", value=plugin.plugin_id, inline=True)
            embed.add_field(name="Version", value=plugin.version, inline=True)
            embed.add_field(name="Author", value=plugin.author, inline=True)
            embed.add_field(name="Module", value=plugin.module_name or "—", inline=True)
            embed.add_field(name="Dependencies", value=", ".join(plugin.dependencies) or "—", inline=True)
            embed.add_field(name="Enabled", value="✅ Ya" if plugin.is_enabled() else "⛔ Tidak", inline=True)
            embed.set_footer(text=f"Kelas: {plugin.__class__.__name__}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        tree.add_command(plugin_group)
