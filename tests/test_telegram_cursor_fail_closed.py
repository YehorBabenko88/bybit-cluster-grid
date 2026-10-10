from pathlib import Path

def test_telegram_cursor_does_not_skip_claimed_unfinished_update():
    source=Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    loop=source.split("async def telegram_loop",1)[1]
    block=loop.split("claimed=await claim_update",1)[1].split("try:\n                        await handle_command",1)[0]
    assert "SELECT status FROM telegram_updates WHERE update_id=$1" in block
    assert 'status!="DONE"' in block
    assert 'raise RuntimeError("Telegram update not completed; cursor held")' in block
    assert block.index('status!="DONE"')<block.index("offset=await commit_telegram_cursor")

def test_telegram_failed_update_is_persisted_for_reconciliation():
    source=Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    loop=source.split("async def telegram_loop",1)[1]
    assert 'await complete_update(db.pool,upd["update_id"],str(e)[:500])' in loop
    assert 'raise RuntimeError("Telegram update not completed; cursor held")' in loop
