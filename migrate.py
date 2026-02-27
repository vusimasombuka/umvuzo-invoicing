from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine
from app.models import Base
import os

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("ERROR: DATABASE_URL not set")
    exit(1)

print(f"Connecting to PostgreSQL...")
engine = create_engine(db_url)
print("Creating tables...")
Base.metadata.create_all(bind=engine)
print("✅ Tables created!")
print("\nCreated:")
for table in Base.metadata.tables.keys():
    print(f"  - {table}")