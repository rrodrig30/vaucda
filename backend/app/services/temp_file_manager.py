"""
Temporary File Manager

Manages session-linked temporary files for document uploads.
Ensures cleanup after Stage 2 completion per HIPAA requirements.
"""

import logging
import os
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

from app.config import settings

logger = logging.getLogger(__name__)


class TempFileManager:
    """
    Temporary file manager for session-linked document storage.

    Files are stored with session prefixes to enable:
    - Retrieval by file ID
    - Cleanup by session ID
    - Automatic expiration cleanup

    File naming convention: {session_id}_{uuid}_{timestamp}.txt
    """

    def __init__(self, temp_dir: Optional[str] = None):
        """
        Initialize temp file manager.

        Args:
            temp_dir: Directory for temp files (defaults to settings.TEMP_FILE_DIR)
        """
        self.temp_dir = Path(temp_dir or settings.TEMP_FILE_DIR)
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Create temp directory if it doesn't exist."""
        try:
            self.temp_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Temp directory ready: {self.temp_dir}")
        except Exception as e:
            logger.error(f"Failed to create temp directory: {e}")
            raise

    def _generate_file_id(self, session_id: str) -> str:
        """
        Generate unique file ID with session prefix.

        Format: {session_id}_{uuid}_{timestamp}

        Args:
            session_id: User session ID

        Returns:
            Unique file ID
        """
        unique_id = uuid.uuid4().hex[:12]
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")

        # Sanitize session_id to prevent path traversal
        safe_session = "".join(c for c in session_id if c.isalnum() or c in "-_")[:32]

        return f"{safe_session}_{unique_id}_{timestamp}"

    def _get_file_path(self, file_id: str) -> Path:
        """
        Get file path for a file ID.

        Args:
            file_id: File ID

        Returns:
            Path to the file
        """
        # Sanitize file_id to prevent path traversal
        safe_id = "".join(c for c in file_id if c.isalnum() or c in "-_")
        return self.temp_dir / f"{safe_id}.txt"

    def save_temp_file(self, content: str, session_id: str) -> str:
        """
        Save extracted text to temp file.

        Args:
            content: Text content to save
            session_id: User session ID

        Returns:
            File ID for later retrieval
        """
        file_id = self._generate_file_id(session_id)
        file_path = self._get_file_path(file_id)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"Saved temp file: {file_id} ({len(content)} chars)")
            return file_id

        except Exception as e:
            logger.error(f"Failed to save temp file {file_id}: {e}")
            raise

    def get_temp_file(self, file_id: str) -> Optional[str]:
        """
        Retrieve temp file content by ID.

        Args:
            file_id: File ID

        Returns:
            File content, or None if not found
        """
        file_path = self._get_file_path(file_id)

        if not file_path.exists():
            logger.warning(f"Temp file not found: {file_id}")
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()

        except Exception as e:
            logger.error(f"Failed to read temp file {file_id}: {e}")
            return None

    def delete_temp_file(self, file_id: str) -> bool:
        """
        Delete temp file.

        Args:
            file_id: File ID

        Returns:
            True if deleted, False if not found or error
        """
        file_path = self._get_file_path(file_id)

        if not file_path.exists():
            logger.debug(f"Temp file already deleted or not found: {file_id}")
            return False

        try:
            file_path.unlink()
            logger.info(f"Deleted temp file: {file_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete temp file {file_id}: {e}")
            return False

    def cleanup_session(self, session_id: str) -> int:
        """
        Delete all temp files for a session.

        Args:
            session_id: User session ID

        Returns:
            Number of files deleted
        """
        # Sanitize session_id
        safe_session = "".join(c for c in session_id if c.isalnum() or c in "-_")[:32]

        deleted_count = 0

        try:
            for file_path in self.temp_dir.glob(f"{safe_session}_*.txt"):
                try:
                    file_path.unlink()
                    deleted_count += 1
                    logger.debug(f"Deleted session file: {file_path.name}")
                except Exception as e:
                    logger.error(f"Failed to delete {file_path}: {e}")

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} temp files for session {safe_session}")

        except Exception as e:
            logger.error(f"Session cleanup error: {e}")

        return deleted_count

    def cleanup_expired(self, max_age_minutes: int = 60) -> int:
        """
        Delete temp files older than max_age_minutes.

        Used for periodic cleanup of abandoned sessions.

        Args:
            max_age_minutes: Maximum file age in minutes

        Returns:
            Number of files deleted
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=max_age_minutes)
        deleted_count = 0

        try:
            for file_path in self.temp_dir.glob("*.txt"):
                try:
                    # Check file modification time
                    mtime = datetime.utcfromtimestamp(file_path.stat().st_mtime)
                    if mtime < cutoff_time:
                        file_path.unlink()
                        deleted_count += 1
                        logger.debug(f"Deleted expired file: {file_path.name}")

                except Exception as e:
                    logger.error(f"Error checking/deleting {file_path}: {e}")

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired temp files")

        except Exception as e:
            logger.error(f"Expired files cleanup error: {e}")

        return deleted_count

    def get_session_file_count(self, session_id: str) -> int:
        """
        Count temp files for a session.

        Args:
            session_id: User session ID

        Returns:
            Number of temp files for the session
        """
        safe_session = "".join(c for c in session_id if c.isalnum() or c in "-_")[:32]

        try:
            return len(list(self.temp_dir.glob(f"{safe_session}_*.txt")))
        except Exception:
            return 0
