import os
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from db import (
    init_db,
    get_or_create_user,
    add_task as db_add_task,
    list_active_tasks,
    delete_by_index,
    list_today_tasks,
    mark_done_by_index,
    clear_done,
    list_high_priority_tasks,
    list_done_tasks,
)
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackContext,
)


REMINDER_INTERVAL_MINUTES = 15  # interval for high priority reminders


def detect_priority(task_text: str) -> str:
    text = task_text.lower()
    high_keywords = ["срочно", "важно", "немедленно", "urgent", "important"]
    medium_keywords = ["скоро", "желательно", "желат.", "medium", "средн"]

    if any(k in text for k in high_keywords):
        return "high"
    if any(k in text for k in medium_keywords):
        return "medium"
    return "low"


def format_task_row(index: int, text: str, priority: str, ts: int) -> str:
    ts_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    return f"{index}. [{priority}] {text} ({ts_str})"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = (
        "Привет! Я бот-ассистент задач. Команды:\n"
        "/add <текст задачи> — добавить задачу\n"
        "/list — показать список задач по приоритетам\n"
        "/delete <номер> — удалить задачу по номеру из списка /list\n"
        "/done <номер> — отметить задачу как выполненную\n"
        "/done_list — показать выполненные задачи\n"
        "/clear — удалить все выполненные задачи\n"
        "/today — список дел на сегодня\n"
        "/help — помощь\n\n"
        "Ключевые слова приоритета в тексте задачи:\n"
        "- высокий: ‘срочно’, ‘важно’, ‘немедленно’ (также ‘urgent’, ‘important’)\n"
        "- средний: ‘скоро’, ‘желательно’\n"
        "- без ключевых слов — низкий приоритет"
    )
    await update.message.reply_text(msg)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def add_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id_int = update.effective_chat.id
    username = update.effective_user.username if update.effective_user else None
    text = (update.message.text or "").strip()

    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await update.message.reply_text(
            "Использование: /add <текст задачи>"
        )
        return

    task_text = parts[1].strip()
    priority = detect_priority(task_text)
    # Ensure user exists, then add task
    user_id = get_or_create_user(chat_id_int, username)
    db_add_task(user_id, task_text, priority)

    await update.message.reply_text(
        f"Задача добавлена: [{priority}] {task_text}"
    )


async def list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id_int = update.effective_chat.id
    tasks = list_active_tasks(chat_id_int)
    if not tasks:
        await update.message.reply_text("Список задач пуст.")
        return

    # tasks: (task_id, text, priority, date, timestamp)
    lines: List[str] = []
    # Group for display
    def add_group(title: str, items: List[tuple]) -> None:
        if not items:
            return
        lines.append(title)
        for i, row in items:
            _, text, pr, _, ts = row
            lines.append(format_task_row(i, text, pr, ts))
        lines.append("")

    # Build grouped view preserving the same ordering
    high = [(i + 1, r) for i, r in enumerate([t for t in tasks if t[2] == "high"])]
    med = [(i + 1 + len(high), r) for i, r in enumerate([t for t in tasks if t[2] == "medium"])]
    low = [(i + 1 + len(high) + len(med), r) for i, r in enumerate([t for t in tasks if t[2] == "low"])]
    add_group("Высокий приоритет:", high)
    add_group("Средний приоритет:", med)
    add_group("Низкий приоритет:", low)

    await update.message.reply_text("\n".join(lines).strip())


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id_int = update.effective_chat.id
    text = (update.message.text or "").strip()

    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("Использование: /delete <номер задачи из /list>")
        return

    try:
        idx = int(parts[1])
    except ValueError:
        await update.message.reply_text("Номер задачи должен быть числом.")
        return

    removed = delete_by_index(chat_id_int, idx)
    if not removed:
        await update.message.reply_text("Неверный номер задачи.")
        return
    _, text_val = removed
    await update.message.reply_text(f"Удалено: {text_val}")


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id_int = update.effective_chat.id
    today_tasks = list_today_tasks(chat_id_int)
    if not today_tasks:
        await update.message.reply_text("На сегодня задач нет.")
        return
    lines = [
        format_task_row(i + 1, t[1], t[2], t[4]) for i, t in enumerate(today_tasks)
    ]
    await update.message.reply_text("\n".join(lines))


async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id_int = update.effective_chat.id
    text = (update.message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await update.message.reply_text("Использование: /done <номер задачи из /list>")
        return
    try:
        idx = int(parts[1])
    except ValueError:
        await update.message.reply_text("Номер задачи должен быть числом.")
        return
    res = mark_done_by_index(chat_id_int, idx)
    if not res:
        await update.message.reply_text("Неверный номер задачи.")
        return
    _, text_val = res
    await update.message.reply_text(f"Отмечено как выполнено: {text_val}")


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id_int = update.effective_chat.id
    deleted = clear_done(chat_id_int)
    await update.message.reply_text(f"Удалено выполненных задач: {deleted}")


async def done_list_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id_int = update.effective_chat.id
    tasks = list_done_tasks(chat_id_int)
    if not tasks:
        await update.message.reply_text("Нет выполненных задач.")
        return
    lines = [
        format_task_row(i + 1, t[1], t[2], t[4]) for i, t in enumerate(tasks)
    ]
    await update.message.reply_text("\n".join(lines))


async def reminder_job(context: CallbackContext) -> None:
    chat_id = context.job.chat_id
    high_tasks = list_high_priority_tasks(chat_id)
    if not high_tasks:
        return
    lines = ["Напоминание о важных задачах:"]
    for i, t in enumerate(high_tasks, start=1):
        # t: (id, text, priority, date, ts)
        lines.append(format_task_row(i, t[1], t[2], t[4]))
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines))


async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Неизвестная команда. Используйте /help для списка доступных команд."
    )


def main() -> None:
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("BOT_TOKEN не установлен. Добавьте его в .env")

    application = ApplicationBuilder().token(bot_token).build()

    application.add_handler(CommandHandler("start", start, block=True))
    application.add_handler(CommandHandler("help", help_cmd, block=True))
    application.add_handler(CommandHandler("add", add_cmd, block=True))
    application.add_handler(CommandHandler("list", list_cmd, block=True))
    application.add_handler(CommandHandler("delete", delete_cmd, block=True))
    application.add_handler(CommandHandler("done", done_cmd, block=True))
    application.add_handler(CommandHandler("done_list", done_list_cmd, block=True))
    application.add_handler(CommandHandler("clear", clear_cmd, block=True))
    application.add_handler(CommandHandler("today", today_cmd, block=True))

    # Periodic reminders for each chat when bot starts receiving updates from it
    # We register a chat-specific repeating job on first message in that chat
    async def ensure_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # If JobQueue is not available (package installed without job-queue extra), skip scheduling
        if not getattr(context, "job_queue", None):
            return
        chat_id = update.effective_chat.id
        job_name = f"reminder-{chat_id}"
        if not context.job_queue.get_jobs_by_name(job_name):
            context.job_queue.run_repeating(
                reminder_job,
                interval=REMINDER_INTERVAL_MINUTES * 60,
                first=REMINDER_INTERVAL_MINUTES * 60,
                name=job_name,
                chat_id=chat_id,
            )

    # Lightweight hook to ensure the reminder job is scheduled for the chat
    application.add_handler(MessageHandler(filters.ALL, ensure_job), group=1)

    # Fallback for unknown commands (same group as command handlers so block=True works)
    application.add_handler(MessageHandler(filters.COMMAND, unknown_message))

    init_db()
    application.run_polling()


if __name__ == "__main__":
    main()


