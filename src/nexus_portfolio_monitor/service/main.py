import asyncio
import logging
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class MonitorService:
    """Monitor service that runs in an asyncio event loop"""
    
    def __init__(self):
        """
        Initialize the monitor service
        """
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
    async def start(self) -> None:
        """Start the monitoring service"""
        if self.running:
            logger.warning("Monitor service is already running")
            return
            
        self.running = True
        logger.info("Starting monitor")
        self._task = asyncio.create_task(self._run())
        
    async def stop(self) -> None:
        """Stop the monitoring service"""
        if not self.running:
            logger.warning("Monitor service is not running")
            return
            
        logger.info("Stopping monitor")
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Monitor stopped")
        
    async def _run(self) -> None:
        """Internal run loop"""
        try:
            while self.running:
                # Currently just an idle loop
                # Future implementation will perform monitoring actions
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.debug("Monitor loop cancelled")
            raise
        except Exception as e:
            logger.exception(f"Error in monitor loop: {e}")
            self.running = False


async def run_service():
    """Run the monitor service until interrupted"""
    service = MonitorService()
    
    try:
        await service.start()
        # Keep the service running
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        await service.stop()


def main():
    """Entry point for the monitor service"""
    asyncio.run(run_service())


if __name__ == "__main__":
    main()
