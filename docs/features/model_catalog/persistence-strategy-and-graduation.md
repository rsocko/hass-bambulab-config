# Persistence Strategy and Database Graduation Path

> **Status**: Strategy approved for Phase 1-4; migration path documented for Phase 6+  
> **Decision**: Stay with SQLite through Phase 5; plan SQLAlchemy ORM migration if multi-sidecar deployment pattern emerges  
> **Last updated**: 2026-04-28

## Current Decision: SQLite Is Right Today

### Rationale

The model_catalog sidecar operates with characteristics that make SQLite optimal for current and near-term phases:

| Factor | Current State | Impact |
|--------|---|---|
| **Data volume** | ~10-15 tables; 10s-100s records per table | SQLite handles this easily; no scale pressure |
| **Concurrency** | Single FastAPI process; lightweight async | SQLite's coarse locking is not a bottleneck |
| **Queries** | Simple lookups by ID/FK; batch refreshes | No complex analytics or joins requiring Postgres |
| **Deployment** | Docker container with persistent volume | Single `.db` file = zero external infrastructure |
| **Operational overhead** | Backup = file copy | Simpler ops than managed Postgres |

### Architecture Boundary Already Protected

The sidecar design has already separated concerns appropriately:

- ✅ **Manyfold's Postgres** stays in Manyfold's control
- ✅ **HA's internal SQLite** remains within HA integration boundary
- ✅ **Sidecar's SQLite** is fully sidecar-owned and portable

This separation ensures that if/when you need to migrate, you're not extracting state from other systems.

---

## Graduation Criteria: When To Migrate

### Trigger Scenarios

| Scenario | Likelihood (5yr) | Migration Urgency | Decision Point |
|---------|---|---|---|
| **Multi-sidecar shared state** — Running 2+ model-catalog instances sharing one data store | Low-Medium | High | During Phase 6-7 planning |
| **Scale to 5k-10k+ model records** | Low | Medium | Monitor during Phase 6 |
| **Complex analytics queries** — Sophisticated filtering across 100k+ rows or rows with full-text search | Very Low | Low | Phase 8+ optional features |
| **Operational requirement** — Compliance/deployment pattern requires external DB (RDS, managed Postgres) | Medium | High | Architectural decision point |
| **Row-level transaction isolation** — Concurrent bulk operations need fine-grained locking | Low | Medium | If Phase 5 bulk intake becomes concurrent |

**Most realistic near-term trigger**: Multi-sidecar architecture (e.g., separate sidecar instances for HA-system-A and HA-system-B sharing curated model library). **Timeline**: 18-36 months out.

---

## Current Implementation: Raw sqlite3

### Baseline Architecture

**Location**: [sidecars/model_catalog/app/db.py](../../sidecars/model_catalog/app/db.py)

```python
# Current approach: raw sqlite3
from sqlite3 import connect, Connection

def connect(db_path: Path) -> Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection

def bootstrap_database(db_path: Path) -> DatabaseInfo:
    connection = connect(db_path)
    try:
        connection.execute(MIGRATION_TABLE_STATEMENT)
        _apply_migrations(connection)
        connection.commit()
        # ... schema validation
    finally:
        connection.close()
    return DatabaseInfo(...)
```

### Query Layer Pattern

All data access is localized in `db.py` module with explicit function signatures:

```python
def create_archive_link(
    *,
    db_path: Path,
    manyfold_model_url: str,
    bambuddy_archive_id: int,
    relationship_type: str,
    # ... other params
) -> ArchiveModelLink:
    connection = connect(db_path)
    try:
        # INSERT with conflict handling
        cursor = connection.execute("""
            INSERT INTO model_catalog_links (...)
            VALUES (...)
        """, (...))
        connection.commit()
    finally:
        connection.close()
    return ArchiveModelLink(...)
```

### Advantages of Current Approach

✅ **Minimal dependencies** — Only stdlib sqlite3  
✅ **Explicit control** — All queries visible; no query builder magic  
✅ **Lightweight** — No ORM overhead for simple operations  
✅ **Portable** — Query logic not coupled to specific DB backend (yet)

### Disadvantages and Migration Risks

⚠️ **Query duplication** — Similar patterns repeated across functions  
⚠️ **Brittle on schema changes** — Adding a column requires updating multiple query strings  
⚠️ **Manual connection management** — `try/finally` blocks everywhere  
⚠️ **Hard to switch backends later** — Requires refactoring all query code (20-30% of sidecar)

---

## Migration Path: SQLAlchemy ORM Abstraction

### When To Implement

**Phase 6** (Search, Ranking, Enrichment Parity) or **Phase 6-7 boundary** if you confirm multi-sidecar is coming in 18 months.

**Effort**: 3-4 hours; adds ~500 LOC; requires 1-2 hours of testing.

### Recommended Approach: Hybrid (ORM + Raw SQL for Complex Queries)

Don't go "full ORM"; use SQLAlchemy for schema definition and simple CRUD, keep raw SQL for complex queries.

#### Step 1: Define Models with Declarative Base

```python
# sidecars/model_catalog/app/models_orm.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, relationship, Session
from datetime import datetime

Base = declarative_base()

class ArchiveLink(Base):
    __tablename__ = "model_catalog_links"
    
    id = Column(Integer, primary_key=True)
    manyfold_model_url = Column(String, nullable=False)
    manyfold_model_public_id = Column(String)
    manyfold_model_file_id = Column(String)
    bambuddy_archive_id = Column(Integer, nullable=False)
    relationship_type = Column(String, nullable=False)
    link_role = Column(String, nullable=False)
    match_method = Column(String, nullable=False)
    match_confidence = Column(String, nullable=False)
    review_state = Column(String, nullable=False)
    review_note = Column(Text)
    is_active = Column(Integer, default=1)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

class ModelRanking(Base):
    __tablename__ = "model_catalog_model_ranking"
    
    manyfold_model_url = Column(String, primary_key=True)
    manyfold_model_public_id = Column(String)
    last_printed_at = Column(String)
    linked_archive_count = Column(Integer, default=0)
    print_count = Column(Integer, default=0)
    recent_score = Column(Integer)
    frequent_score = Column(Integer)
    common_score = Column(Integer)
    refreshed_at = Column(String, nullable=False)

class WorkingGroup(Base):
    __tablename__ = "working_groups"
    
    id = Column(Integer, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    stage = Column(String, nullable=False)
    notes = Column(Text)
    primary_file_path = Column(String)
    folder_hint = Column(String)
    related_manyfold_model_id = Column(String)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
    
    items = relationship("WorkingItem", back_populates="group")

class WorkingItem(Base):
    __tablename__ = "working_items"
    
    id = Column(Integer, primary_key=True)
    working_group_id = Column(Integer, ForeignKey("working_groups.id"), nullable=False)
    file_path = Column(String, nullable=False)
    file_hash = Column(String)
    file_size = Column(Integer)
    item_role = Column(String, default="supporting")
    source_metadata_json = Column(Text, default="{}")
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
    
    group = relationship("WorkingGroup", back_populates="items")
```

#### Step 2: Abstract the Connection Layer

```python
# sidecars/model_catalog/app/db_orm.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from pathlib import Path

def get_engine(db_url: str):
    """
    Create engine for SQLite or Postgres.
    
    Examples:
        SQLite: sqlite:///model_catalog.db
        Postgres: postgresql://user:pass@host/dbname
    
    SQLite-specific: Use StaticPool to avoid threading issues with async
    """
    if db_url.startswith("sqlite"):
        return create_engine(
            db_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        # Postgres or other backend
        return create_engine(db_url, echo=False)

def get_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    return SessionLocal()

def init_db(db_url: str):
    """Initialize schema from ORM models."""
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    return engine
```

#### Step 3: Refactor Query Functions to Use ORM

```python
# sidecars/model_catalog/app/db_queries.py
from sqlalchemy.orm import Session
from .models_orm import ArchiveLink, ModelRanking
from .models import ArchiveModelLink  # Keep dataclass for DTO

def create_archive_link_orm(
    session: Session,
    *,
    manyfold_model_url: str,
    manyfold_model_public_id: str | None,
    manyfold_model_file_id: str | None,
    bambuddy_archive_id: int,
    relationship_type: str,
    # ... other params
) -> ArchiveModelLink:
    """Create archive-to-model link using ORM."""
    link = ArchiveLink(
        manyfold_model_url=manyfold_model_url,
        manyfold_model_public_id=manyfold_model_public_id,
        manyfold_model_file_id=manyfold_model_file_id,
        bambuddy_archive_id=bambuddy_archive_id,
        relationship_type=relationship_type,
        # ...
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    session.add(link)
    session.commit()
    session.refresh(link)
    return _convert_to_dto(link)

def read_archive_links_orm(
    session: Session,
    archive_id: int,
    active_only: bool = True,
) -> list[ArchiveModelLink]:
    """Read archive links using ORM query."""
    query = session.query(ArchiveLink).filter(
        ArchiveLink.bambuddy_archive_id == archive_id
    )
    if active_only:
        query = query.filter(ArchiveLink.is_active == 1)
    
    rows = query.order_by(ArchiveLink.created_at.desc()).all()
    return [_convert_to_dto(row) for row in rows]

def _convert_to_dto(orm_obj: ArchiveLink) -> ArchiveModelLink:
    """Convert ORM model to dataclass DTO."""
    return ArchiveModelLink(
        id=orm_obj.id,
        manyfold_model_url=orm_obj.manyfold_model_url,
        manyfold_model_public_id=orm_obj.manyfold_model_public_id,
        # ...
    )
```

#### Step 4: Update FastAPI Endpoints to Use ORM

```python
# sidecars/model_catalog/app/main.py
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from .db_orm import get_engine, get_session
from .db_queries import create_archive_link_orm, read_archive_links_orm

app = FastAPI()
engine = get_engine(os.getenv("DATABASE_URL", "sqlite:///model_catalog.db"))

@app.post("/api/archive-links/{archive_id}")
async def create_link(archive_id: int, request: CreateLinkRequest):
    """Create archive-to-model link."""
    session = get_session(engine)
    try:
        link = create_archive_link_orm(
            session,
            manyfold_model_url=request.model_url,
            bambuddy_archive_id=archive_id,
            # ...
        )
        return {"id": link.id, "status": "created"}
    finally:
        session.close()
```

#### Step 5: Configuration and Environment

```python
# sidecars/model_catalog/app/settings.py
from pydantic import BaseSettings

class Settings(BaseSettings):
    # Current (stays the same)
    db_path: Path = Path("/data/model_catalog.db")
    
    # New (for ORM)
    database_url: str | None = None  # If set, use it; otherwise fall back to db_path
    
    @property
    def db_url_for_orm(self) -> str:
        """Return SQLAlchemy-compatible database URL."""
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path}"
```

---

## Advantages of SQLAlchemy Approach

### For Phase 1-5 (Stay SQLite)

✅ **No operational change** — Still use SQLite locally  
✅ **Phased refactoring** — Do it during Phase 6 without touching Phase 1-5 features  
✅ **Backward compatible** — Old raw sql3 queries can coexist with ORM queries during transition

### For Phase 6+ (If Multi-Sidecar Emerges)

✅ **Switch backends with one config change**:
```bash
# Local development: SQLite
DATABASE_URL=sqlite:///model_catalog.db

# Production multi-sidecar: Postgres
DATABASE_URL=postgresql://user:pass@shared-postgres/model_catalog
```

✅ **Same query code works everywhere** — No SQL dialect tricks needed (SQLAlchemy abstracts them)

✅ **Built-in connection pooling** — Postgres connection pool configured automatically

✅ **Easier testing** — Can use in-memory SQLite for tests:
```python
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
# Run tests against in-memory DB
```

---

## Migration Timeline and Checkpoints

### Phase 1-5: Keep Current sqlite3 (No Changes)

- Continue with raw sqlite3 approach in [db.py](../../sidecars/model_catalog/app/db.py)
- No refactoring needed
- Code remains simple and dependency-light

### Phase 6: Plan Evaluation (2-3 weeks before)

**Questions to answer**:
- [ ] Is multi-sidecar architecture planned within 18 months?
- [ ] Will you deploy to environment with managed Postgres already running?
- [ ] Has data volume grown enough that you need analytics queries?

**If ANY answer is "yes"**: Schedule SQLAlchemy refactoring for Phase 6 start.  
**If ALL "no"**: Defer to Phase 7 or skip if not needed.

### Phase 6-7: SQLAlchemy Migration (If Triggered)

**Timeline**: 3-4 working days

1. **Day 1**: Create `models_orm.py` with all ORM model definitions
2. **Day 2**: Create `db_orm.py` connection/session management
3. **Day 3**: Refactor `db_queries.py` to use ORM (keep DTOs for API contracts)
4. **Day 4**: Update endpoints in `main.py` to use ORM queries; run full test suite
5. **Testing**: Verify all existing tests pass; add ORM-specific tests

**Validation gates**:
- [ ] All existing tests pass (archive linkage, ranking, working groups)
- [ ] Postgres connection works in test environment
- [ ] SQLite still works (no regressions)
- [ ] No performance degradation vs. raw sqlite3

### Phase 8+: Ongoing

- Monitor for new data access patterns
- Consider migrations to Postgres if/when multi-sidecar stabilizes
- Keep escape hatch documented in architecture guides

---

## Schema Migration Strategy (ORM-Safe)

### Current Approach (Raw sqlite3)

**Location**: [db.py MIGRATIONS tuple](../../sidecars/model_catalog/app/db.py#L25-L168)

```python
MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1, ("""CREATE TABLE ...""", ...)),
    (2, ("""ALTER TABLE ...""", ...)),
    # ...
)
```

### With SQLAlchemy ORM

Keep schema migration **separate from ORM model definitions**. Use Alembic for reproducible migrations:

```bash
# Initialize Alembic
cd sidecars/model_catalog
alembic init alembic

# After changing ORM model definitions
alembic revision --autogenerate -m "Add new field to working_groups"

# Apply migrations
alembic upgrade head
```

**Why separate**:
- ORM models define the "target" schema
- Alembic migrations define the "steps" to get there
- This works the same whether you use SQLite or Postgres

---

## Decision Checkpoint: Phase 6

**Document in your Phase 6 planning**:

- [ ] Confirm multi-sidecar architecture decision
- [ ] Review data volume and query complexity
- [ ] Decide: "Refactor to SQLAlchemy now" or "Stay sqlite3, defer indefinitely"
- [ ] If refactor: Schedule 3-4 days; plan testing sprints

---

## Summary: What You're Choosing

| Timeline | Decision | Action | Impact |
|----------|----------|--------|--------|
| **Now (Phase 1-5)** | Stay sqlite3 | Continue current [db.py](../../sidecars/model_catalog/app/db.py) code | Zero ops changes |
| **Phase 6 (6mo+)** | Evaluate | Answer trigger questions | Decide on refactoring |
| **Phase 6-7 (if triggered)** | Migrate to SQLAlchemy | 3-4 day refactoring sprint | Enable Postgres/multi-sidecar if needed |
| **Phase 8+** | Operate** | Monitor patterns | Grow or stay as-is |

**You're not committing to Postgres.** You're documenting:
1. Why SQLite is right today
2. When you'd know to switch
3. How to switch (step-by-step)
4. What the costs and benefits are

That's good architecture.

---

## Related Documentation

- **Current schema**: [Model Catalog ER Diagrams](model-catalog-er-diagrams.md)
- **Current implementation**: [db.py](../../sidecars/model_catalog/app/db.py)
- **Architecture**: [architecture-overview.md](architecture-overview.md#model-catalog-persistence-direction)
- **Post-Manyfold transition**: [post-manyfold-transition-plan-2026-04.md](post-manyfold-transition-plan-2026-04.md)
