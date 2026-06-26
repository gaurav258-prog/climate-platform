import logging
from abc import ABC, abstractmethod

from core.db.models import SatelliteObservation
from core.db.session import get_session

logger = logging.getLogger(__name__)

ADAPTER_VERSION = "0.1.0"


class BaseAdapter(ABC):
    """
    Abstract base for all satellite/data source adapters.

    Contract:
    - fetch()            — pull raw records from the external source
    - to_observations()  — convert raw records to SatelliteObservation ORM objects
    - run()              — orchestrates fetch → convert → write, returns count written

    The rest of the platform never knows which adapter produced an observation.
    Provider identity is captured in source_provider but never used for routing.
    This is the Provider Abstraction Layer.
    """

    source_provider: str  # set by each subclass, e.g. "nasa_firms_viirs"
    adapter_version: str = ADAPTER_VERSION

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Pull raw data from the source. Return list of raw records."""

    @abstractmethod
    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        """Convert raw records to SatelliteObservation ORM objects."""

    def run(self) -> int:
        """Fetch, convert, and write observations. Returns count written."""
        logger.info(f"[{self.__class__.__name__}] starting ingestion run")

        raw = self.fetch()
        logger.info(f"[{self.__class__.__name__}] fetched {len(raw)} raw records")

        observations = self.to_observations(raw)
        good = sum(1 for o in observations if o.quality_flag == 0)
        flagged = sum(1 for o in observations if o.quality_flag > 0)
        logger.info(f"[{self.__class__.__name__}] parsed: {good} good, {flagged} flagged")

        if not observations:
            logger.info(f"[{self.__class__.__name__}] nothing to write")
            return 0

        with get_session() as session:
            session.add_all(observations)

        logger.info(f"[{self.__class__.__name__}] wrote {len(observations)} observations")
        return len(observations)
