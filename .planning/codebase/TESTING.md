# Testing Patterns

**Analysis Date:** 2026-03-31

## Test Framework

**Runner:**
- pytest with Python 3.14 (`.venv` at project root)
- No explicit pytest configuration file; uses test discovery defaults
- Test location: `tests/` directory alongside project root

**Assertion Library:**
- pytest built-in `assert` statements with comparison operators
- No external assertion library (standard pytest patterns)

**Run Commands:**
```bash
pytest tests/                    # Run all tests
pytest tests/ -v                 # Verbose output with test names
pytest tests/ --tb=short         # Brief traceback format
pytest tests/ -k "test_rss"      # Run tests matching pattern
```

**Coverage:**
- No explicit coverage configuration; use `pytest --cov` if needed
- Current state: 283 tests pass (from CLAUDE.md), no documented coverage target

## Test File Organization

**Location:**
- Co-located in `tests/` directory mirroring source structure
- Pattern: `test_<module>.py` or `test_<feature>.py`
- Fixtures shared via `conftest.py` at tests root

**Naming:**
- Test files: `test_*.py` (e.g., `test_rss_collector.py`, `test_event_aggregation.py`)
- Test functions: `test_<action>_<context>` (e.g., `test_rss_collect_returns_list`, `test_aggregate_creates_event`)
- Parametrize not heavily used; individual test functions preferred

**Structure:**
```
tests/
├── conftest.py                    # Global fixtures (scheduler mock)
├── test_event_aggregation.py      # Event aggregation tests
├── test_rss_collector.py          # RSS collector tests
├── test_keywords.py               # Keyword tagging tests
├── test_health_active_sources.py  # Source health checks
└── ... (20+ test files)
```

## Test Structure

**Suite Organization:**

```python
# conftest.py: Global autouse fixture
@pytest.fixture(autouse=True)
def _no_scheduler(request):
    """Patch CollectorScheduler for every test to prevent background threads."""
    with patch("scheduler.CollectorScheduler.start", return_value=None), \
         patch("scheduler.CollectorScheduler.shutdown", return_value=None):
        yield
```

**Patterns:**

1. **In-memory database per test:**
   ```python
   @pytest.fixture
   def db_session():
       engine = create_engine("sqlite:///:memory:")
       Base.metadata.create_all(engine)
       session = sessionmaker(bind=engine)()
       yield session
       session.close()
   ```

2. **Factory helper for test data:**
   ```python
   def _make_article(
       session: Session,
       source: str,
       narrative_tags: list[str],
       relevance: int = 3,
       hours_ago: float = 1.0,
   ) -> Article:
       now = datetime.utcnow()
       article = Article(source=source, ...)
       session.add(article)
       session.commit()
       return article
   ```

3. **Setup/Teardown:**
   - Implicit: Fixture setup in `@pytest.fixture`, cleanup via context manager or yield
   - Session commits within test setup; no explicit teardown needed

4. **Assertion pattern:**
   ```python
   events = db_session.query(Event).all()
   assert len(events) == 1
   assert event.narrative_tag == "nvidia-earnings"
   assert event.source_count == 2
   ```

## Mocking

**Framework:** Python `unittest.mock` (builtin)

**Patterns:**

1. **Patch at module import level:**
   ```python
   with patch("collectors.rss.feedparser.parse", return_value=EMPTY_FEED), \
        patch("collectors.rss.config.RSS_FEEDS", FAKE_FEEDS):
       assert isinstance(RSSCollector().collect(), list)
   ```

2. **MagicMock for complex objects:**
   ```python
   FAKE_ENTRY = MagicMock()
   FAKE_ENTRY.link = "https://example.com/post/1"
   FAKE_ENTRY.title = "Test Post"
   FAKE_ENTRY.summary = "Some content"
   
   GOOD_FEED = MagicMock()
   GOOD_FEED.entries = [FAKE_ENTRY]
   GOOD_FEED.bozo = False
   ```

3. **Side-effect for conditional mocking:**
   ```python
   def side_effect(url, **kw):
       if "broken" in url:
           raise Exception("timeout")
       return GOOD_FEED
   
   with patch("collectors.rss.feedparser.parse", side_effect=side_effect):
       result = RSSCollector().collect()
   ```

**What to Mock:**
- External services (feedparser, HTTP requests, file I/O)
- System dependencies (scheduler background threads)
- Configuration at test time (e.g., `config.RSS_FEEDS`)

**What NOT to Mock:**
- Core business logic (aggregation, filtering, scoring)
- Database layers (use in-memory SQLite instead)
- Application context (use actual FastAPI TestClient if available)

## Fixtures and Factories

**Test Data:**

1. **Database fixture (`db_session`)** — In-memory SQLite per test
   - Located: `test_event_aggregation.py`, `test_event_models.py`
   - Scope: Function-level (fresh DB per test)

2. **Factory function (`_make_article`)** — Create test articles
   ```python
   def _make_article(
       session: Session,
       source: str,
       narrative_tags: list[str],
       relevance: int = 3,
       hours_ago: float = 1.0,
   ) -> Article:
       # Creates, commits, and returns Article instance
   ```

3. **MagicMock constants** — Predefined test objects
   - `FAKE_ENTRY`: Parsed feed entry with common attributes
   - `GOOD_FEED`, `EMPTY_FEED`: Feed parse results
   - `FAKE_FEEDS`: Config list for RSS test

**Location:**
- Global fixtures: `tests/conftest.py`
- Per-test-file fixtures: Top of each test file (e.g., `db_session` in test_event_aggregation.py)
- Mock data constants: Inline in test files near usage (e.g., `FAKE_ENTRY` in test_rss_collector.py)

**Cleanup:**
- Explicit: `session.close()` in fixture
- Implicit: In-memory DB dropped when connection closes

## Coverage

**Requirements:** No explicit target; 283 tests pass locally

**View Coverage:**
```bash
pytest --cov=collectors --cov=db --cov=tagging --cov=events --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Scope: Individual functions and classes (collectors, taggers, models)
- Approach: Mock external dependencies, test with synthetic data
- Examples:
  - `test_rss_parses_entry_to_dict()` — RSS collector entry parsing
  - `test_crypto_tags()` — Keyword tagging logic
  - `test_aggregate_creates_event()` — Event aggregation with mock articles

**Integration Tests:**
- Scope: API endpoints, database operations, collector + save flow
- Approach: Use in-memory DB, real logic, no external HTTP
- Examples:
  - `test_health_active_sources()` — Health check endpoint with registry
  - `test_personalized_feed()` — Feed API with user weights
  - `test_event_api()` — Event endpoint with aggregated data

**E2E Tests:**
- Framework: Not currently used
- Recommendation: Use Playwright for critical frontend flows (feed → event → constellation)

## Common Patterns

**Async Testing:**
- Not heavily used in current codebase
- FastAPI app tested via TestClient in integration tests if needed
- Collectors are sync; async logic (event aggregation scheduler) mocked in conftest

**Error Testing:**

```python
# Graceful failure handling
def test_rss_broken_feed_skipped_gracefully():
    def side_effect(url, **kw):
        if "broken" in url:
            raise Exception("timeout")
        return GOOD_FEED
    
    with patch("collectors.rss.feedparser.parse", side_effect=side_effect):
        result = RSSCollector().collect()
    
    assert len(result) == 1  # only good feed processed
```

**Dedup Testing:**
- `test_source_id_deterministic()` — Same input → same source_id for dedup
- `test_duplicate_skipped_gracefully()` — IntegrityError caught and logged

**Data Transformation Testing:**

```python
# Keyword extraction
def test_title_weighted_higher():
    tags = tag_article("Bitcoin crash", "AI news and semiconductor updates")
    assert tags[0] == "crypto"  # Title keyword ranked first
```

**State Testing:**

```python
def test_aggregate_updates_existing_event(db_session: Session):
    _make_article(db_session, "hackernews", ["test-tag"], relevance=4, hours_ago=2)
    run_aggregation(db_session)
    
    events = db_session.query(Event).all()
    assert len(events) == 1
    assert events[0].source_count == 1
    
    # Add another article, re-aggregate
    _make_article(db_session, "rss", ["test-tag"], relevance=2, hours_ago=0.5)
    run_aggregation(db_session)
    
    events = db_session.query(Event).all()
    assert len(events) == 1
    assert events[0].source_count == 2  # Updated
```

---

*Testing analysis: 2026-03-31*
