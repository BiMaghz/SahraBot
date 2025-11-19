import logging
import asyncio

from aiohttp import web

from app.core.config import Settings

logger = logging.getLogger(__name__)

async def webhook_handler(request: web.Request):
    settings: Settings = request.app["settings"]
    
    if request.headers.get("X-Webhook-Secret") != settings.WEBHOOK_SECRET:
        logger.warning("Webhook received with invalid signature.")
        return web.Response(status=403, text="Invalid signature")
    
    try:
        payload = await request.json()
        queue: asyncio.Queue = request.app["queue"]

        if isinstance(payload, dict) and "action" in payload:
            await queue.put(payload)
            logger.info("Successfully enqueued 1 event from webhook.")
            return web.Response(status=200, text="OK")
        
        logger.warning(f"Webhook received unexpected payload format: {type(payload)}")
        return web.Response(status=400, text="Bad Request: Expected a JSON object.")
        
    except Exception as e:
        logger.error(f"Error in webhook handler: {e}", exc_info=True)
        return web.Response(status=500, text="Internal Server Error")

async def start_webhook_server(bot, queue, settings: Settings):
    app = web.Application()
    
    app["bot"] = bot
    app["queue"] = queue
    app["settings"] = settings
    
    app.router.add_post("/webhook", webhook_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.WEBHOOK_ADDRESS, settings.WEBHOOK_PORT)
    
    try:
        await site.start()
        logger.info(f"Webhook server started on http://{settings.WEBHOOK_ADDRESS}:{settings.WEBHOOK_PORT}")
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Webhook server failed to start: {e}")
    finally:
        await runner.cleanup()