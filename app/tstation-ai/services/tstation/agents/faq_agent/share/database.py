# shared/database.py
import logging
from config.settings import settings
from typing import Optional, List, Dict, Any
import asyncio
import oracledb

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Database Manager for oracle using oracledb, directly.
    Replaces the incompatible databases 'databases' library.
    """
    
    # def __init__(self):
    #     self.db_type = settings.db_type
    #     self.database: Optional[databases.Database] = None
    #     self._setup_database()
    
    # def _setup_database(self):
    #     """Setup database connection based on type"""
        
    #     if self.db_type == "oracle":
    #         # Initialize Oracle client
    #         try:
    #             # Try to use thick client (cx_Oracle)
    #             cx_Oracle.init_oracle_client()
    #             print("✓ Using cx_Oracle thick client")
    #         except:
    #             # Fall back to thin client (oracledb)
    #             print("✓ Using oracledb thin client")
            
    #         # For Oracle with databases library, use cx_Oracle driver
    #         self.database = databases.Database(
    #             settings.database_url,
    #             min_size=settings.db_pool_min,
    #             max_size=settings.db_pool_max
    #         )
        
    #     elif self.db_type == "postgresql":
    #         self.database = databases.Database(
    #             settings.database_url,
    #             min_size=settings.db_pool_min,
    #             max_size=settings.db_pool_max
    #         )
        
    #     elif self.db_type == "mysql":
    #         self.database = databases.Database(
    #             settings.database_url,
    #             min_size=settings.db_pool_min,
    #             max_size=settings.db_pool_max
    #         )
        
    #     else:
    #         raise ValueError(f"Unsupported database type: {self.db_type}")

    def __init__(self):
        self.pool = None
    
    async def connect(self):
        """Connect to Oracle Connection Pool"""
        if not self.pool:
            return
        
        logger.info("Initializing Oracle Connection Pool...")
        print("Initializing Oracle Connection Pool...")

        try:
            dsn = f"{settings.db_host}:{settings.db_port}/{settings.db_service_name}"

            # Create connection pool
            # We run this in an executor because creating a pool can be blocking
            loop = asyncio.get_running_loop()
            self.pool = await loop.run_in_executor(
                None,
                lambda: oracledb.create_pool(
                    user=settings.db_user,
                    password=settings.db_password,
                    dsn=dsn,
                    min=1,
                    max=5,
                    increment=1
                )
            )
            print("✓ Oracle Connection Pool created")
        except Exception as e:
            print(f"✗ Failed to create Oracle Connection Pool: {e}")
            logger.error(f"Oracle Connection Error: {e}")
            # We don't raise here to allow the app to start,
            # but subsequent DB operations will fail.
    
    async def disconnect(self):
        """Disconnect from database"""
        if self.pool:
            self.pool.close()
            self.pool = None
            print("Oracle Connection Pool closed")
    
    
    async def fetch_all(self, query: str, params: dict = None) -> List[Dict[str, Any]]:
        """Fetch all rows (Async wrapper)"""
        if not self.pool:
            await self.connect()
            if not self.pool:
                raise ConnectionError("Database not connected")
            
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_all_sync, query, params)

    def _fetch_all_sync(self, query: str, params: dict = None):
        """Synchronous fetch with LOB handling"""
        try:
            with self.pool.acquire() as conn:
                conn.outputtypehandler = self._output_type_handler
                with conn.cursor() as cursor:
                    if params:
                        cursor.execute(query, params)
                    else:
                        cursor.execute(query)
                    
                    if cursor.description:
                        columns = [col[0].lower() for col in cursor.description]
                        rows = cursor.fetchall()
                        return [dict(zip(columns, row)) for row in rows]
                    return []
        except Exception as e:
            print(f"DB Query Error: {e}")
            return []

    @staticmethod
    def _output_type_handler(cursor, name, default_type, size, precision, scale):
        """Fix for Oracle LOB/CLOB errors"""
        if default_type == oracledb.CLOB:
            return cursor.var(oracledb.STRING, arraysize=cursor.arraysize)
        if default_type == oracledb.BLOB:
            return cursor.var(oracledb.BYTES, arraysize=cursor.arraysize)

db_manager = DatabaseManager()