"""
Database engine and session setup.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_plants_qr_unique_per_owner(conn) -> None:
    """Replace legacy UNIQUE(qr_code) with UNIQUE(owner_id, qr_code) for SQLite."""
    from sqlalchemy import text

    rows = conn.execute(text("PRAGMA index_list('plants')")).fetchall()
    for row in rows:
        unique = row[2] if len(row) > 2 else 0
        if not unique:
            continue
        idx_name = row[1]
        info = conn.execute(text(f'PRAGMA index_info("{idx_name}")')).fetchall()
        col_names = [r[2] for r in info]
        if col_names == ["qr_code"]:
            conn.execute(text(f'DROP INDEX "{idx_name}"'))
            break
    exists = conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='index' AND name='uq_plants_owner_qr'")
    ).fetchone()
    if not exists:
        conn.execute(text("CREATE UNIQUE INDEX uq_plants_owner_qr ON plants (owner_id, qr_code)"))


def run_sqlite_migrations(engine) -> None:
    """
    Lightweight idempotent SQLite migrations applied on every startup. SQLAlchemy's
    create_all only creates *missing* tables — it never adds columns to an existing
    table — so we hand-add columns here.

    Currently:
      * telemetry.plant_id (Phase 1 of the GMO research design)
      * recording_sessions.scenario / dummy_stream / stream_interval_sec (Phase 2)
      * plants.created_by backfill from owner_id when NULL (supports list_plants reclaim)
    """
    if "sqlite" not in str(engine.url):
        return
    from sqlalchemy import text

    def _add_col_if_missing(conn, table: str, col: str, ddl: str) -> None:
        cols = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
        if col not in cols:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))

    with engine.begin() as conn:
        # Telemetry: per-plant index column for fast graph queries.
        _add_col_if_missing(conn, "telemetry", "plant_id", "plant_id INTEGER")
        conn.execute(
            text(
                """
                UPDATE telemetry SET plant_id = (
                    SELECT rs.plant_id FROM recording_sessions rs WHERE rs.id = telemetry.session_id
                )
                WHERE session_id IS NOT NULL AND plant_id IS NULL
                """
            )
        )

        # RecordingSession: dummy-stream metadata so the UI can reflect what's running.
        _add_col_if_missing(conn, "recording_sessions", "scenario", "scenario VARCHAR(32)")
        _add_col_if_missing(conn, "recording_sessions", "dummy_stream",
                            "dummy_stream BOOLEAN NOT NULL DEFAULT 0")
        _add_col_if_missing(conn, "recording_sessions", "stream_interval_sec",
                            "stream_interval_sec INTEGER")

        # One-time: ensure every existing plant has a control profile (after plant_control table exists)
        if "plant_control" in [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]:
            from services.default_control_profile import default_control_json

            dflt = default_control_json()
            sub = "SELECT p.id FROM plants p LEFT JOIN plant_control pc ON pc.plant_id = p.id WHERE pc.plant_id IS NULL"
            for (pid,) in conn.execute(text(sub)).fetchall():
                conn.execute(
                    text("INSERT INTO plant_control (plant_id, profile_json) VALUES (:id, :j)"),
                    {"id": pid, "j": dflt},
                )

        # Plants: per-user ownership (nullable until bootstrap_auth fills legacy owner)
        _add_col_if_missing(conn, "plants", "owner_id", "owner_id INTEGER")
        _add_col_if_missing(conn, "plants", "created_by", "created_by INTEGER")
        # Align created_by with owner when missing so list_plants reclaim can use created_by
        conn.execute(
            text(
                "UPDATE plants SET created_by = owner_id "
                "WHERE created_by IS NULL AND owner_id IS NOT NULL"
            )
        )

        # QR was globally unique; scope (owner_id, qr_code) so different accounts can reuse TM-S001.
        _migrate_plants_qr_unique_per_owner(conn)

        # FR10: persisted anomaly detector outputs (create_all only adds missing tables; old SQLite files need this).
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS anomaly_detection_events (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    plant_id INTEGER NOT NULL,
                    session_id INTEGER,
                    telemetry_id INTEGER,
                    created_at DATETIME NOT NULL,
                    anomaly_type VARCHAR(32) NOT NULL,
                    variable VARCHAR(64) NOT NULL,
                    severity VARCHAR(16) NOT NULL,
                    message TEXT,
                    detail_json TEXT,
                    FOREIGN KEY(plant_id) REFERENCES plants(id) ON DELETE CASCADE,
                    FOREIGN KEY(session_id) REFERENCES recording_sessions(id),
                    FOREIGN KEY(telemetry_id) REFERENCES telemetry(id) ON DELETE SET NULL
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_anomaly_detection_events_plant_id ON anomaly_detection_events (plant_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_anomaly_detection_events_created_at ON anomaly_detection_events (created_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_anomaly_detection_events_session_id ON anomaly_detection_events (session_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_anomaly_detection_events_telemetry_id ON anomaly_detection_events (telemetry_id)"
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS telemetry_ml_predictions (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    plant_id INTEGER NOT NULL,
                    telemetry_id INTEGER NOT NULL,
                    predicted_class VARCHAR(32) NOT NULL,
                    feature_version VARCHAR(16) NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(plant_id) REFERENCES plants(id) ON DELETE CASCADE,
                    FOREIGN KEY(telemetry_id) REFERENCES telemetry(id) ON DELETE CASCADE,
                    CONSTRAINT uq_telemetry_ml_predictions_telemetry_id UNIQUE (telemetry_id)
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_telemetry_ml_predictions_plant_id ON telemetry_ml_predictions (plant_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_telemetry_ml_predictions_created_at ON telemetry_ml_predictions (created_at)"
            )
        )


def bootstrap_auth(engine) -> None:
    """
    Ensure at least one user exists for FK targets; backfill plant.owner_id and
    orphan recording session started_by. Safe to call on every startup (idempotent).
    """
    from sqlalchemy.orm import sessionmaker

    from config import settings
    from models.plant import Plant
    from models.session import RecordingSession
    from models.user import User
    from services.auth_service import create_user, hash_password

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        n = db.query(User).count()
        if n == 0 and settings.TERRA_BOOTSTRAP_DEMO_USER:
            create_user(
                db,
                settings.TERRA_DEMO_EMAIL,
                settings.TERRA_DEMO_PASSWORD,
                is_admin=False,
            )
        elif n == 0:
            # Minimal user row so plants can reference owner_id=1
            u = User(
                email=settings.TERRA_DEMO_EMAIL,
                password_hash=hash_password("!no_login_bootstrap"),
                is_active=False,
                is_admin=False,
            )
            db.add(u)
            db.commit()

        first = db.query(User).order_by(User.id.asc()).first()
        if first:
            # 1) Prefer the account that created the row (avoids mis-assigning to user 1).
            db.query(Plant).filter(Plant.owner_id.is_(None), Plant.created_by.isnot(None)).update(
                {Plant.owner_id: Plant.created_by}, synchronize_session=False
            )
            # 2) Remaining orphan plants → first user (legacy / no created_by)
            db.query(Plant).filter(Plant.owner_id.is_(None)).update(
                {Plant.owner_id: first.id}, synchronize_session=False
            )
            # 3) Fix rows where a prior bootstrap set owner to user 1 but created_by is another user
            db.query(Plant).filter(
                Plant.created_by.isnot(None),
                Plant.owner_id != Plant.created_by,
            ).update(
                {Plant.owner_id: Plant.created_by},
                synchronize_session="fetch",
            )
            db.query(RecordingSession).filter(
                RecordingSession.started_by.is_(None),
                RecordingSession.ended_at.is_(None),
            ).update({RecordingSession.started_by: first.id}, synchronize_session=False)
            db.commit()
    finally:
        db.close()
