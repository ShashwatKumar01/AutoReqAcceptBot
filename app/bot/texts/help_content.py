"""Help text and keyboards for /help and menu:help."""


def build_help_text(is_super_admin: bool = False) -> str:
    lines = [
        "❓ <b>Command reference</b>",
        "",
        "New here? Run <b>/tutorial</b> first — step-by-step setup.",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "<b>Everyone</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        "/start — Welcome screen and add-bot buttons",
        "/tutorial — Interactive setup guide (recommended)",
        "/help — This command list",
        "/menu — Full control panel (after a chat is connected)",
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "<b>Chat admins</b> <i>(after bot is added to your group/channel)</i>",
        "━━━━━━━━━━━━━━━━━━━━",
        "/mychannels — List chats linked to your account",
        "/refresh — Same as mychannels (refresh list)",
        "/settings — Open main menu / configuration",
        "/welcome — Welcome DM: text, media, buttons, timing",
        "/goodbye — Goodbye message when members leave",
        "/stats — Join requests and welcome stats per chat",
        "/broadcast — Message members who joined via your chats",
        "/plan — Your subscription plan",
        "/connect &lt;chat_id&gt; — Register a chat by ID",
        "/disconnect &lt;chat_id&gt; — Unlink a chat",
        "/captcha on|off — Captcha before approve (in group or by chat id)",
        "",
        "<b>Tip:</b> Forward any message from a group/channel here to see its "
        "<code>chat_id</code> and connection status.",
    ]

    if is_super_admin:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━",
            "<b>Super admin only</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "/admin — Bot owner panel + web dashboard link",
            "/users — Total users in database",
            "/chats — Total connected chats (global)",
            "/system — Health summary",
            "/master_broadcast — Message every stored user",
            "/dbcheck — Quick MongoDB counters",
            "",
            "Web dashboard: use <code>ADMIN_API_SECRET</code> at <b>/admin/</b>",
        ])

    return "\n".join(lines)
