"""
Linux Game Benchmark API Server.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
import sqlite3
import json
from pathlib import Path

app = FastAPI(title="Linux Game Benchmark API", version="1.0.0")

# Database path
DB_PATH = Path("/opt/lgb/benchmarks.db")


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS benchmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            steam_app_id INTEGER NOT NULL,
            game_name TEXT NOT NULL,
            resolution TEXT NOT NULL,
            gpu TEXT,
            cpu TEXT,
            os TEXT,
            kernel TEXT,
            ram_gb INTEGER,
            fps_avg REAL,
            fps_min REAL,
            fps_1low REAL,
            fps_01low REAL,
            stutter_rating TEXT,
            consistency_rating TEXT,
            steam_id TEXT,
            steam_name TEXT,
            client_version TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# Initialize database on startup
init_db()


class BenchmarkSubmission(BaseModel):
    steam_app_id: int
    game_name: str
    resolution: str
    system: Dict[str, Any]
    metrics: Dict[str, Any]
    submitter: Optional[Dict[str, str]] = None
    client_version: Optional[str] = None


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/api/v1/benchmark")
async def submit_benchmark(data: BenchmarkSubmission):
    """Submit a new benchmark result."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO benchmarks (
            steam_app_id, game_name, resolution,
            gpu, cpu, os, kernel, ram_gb,
            fps_avg, fps_min, fps_1low, fps_01low,
            stutter_rating, consistency_rating,
            steam_id, steam_name, client_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.steam_app_id,
        data.game_name,
        data.resolution,
        data.system.get("gpu"),
        data.system.get("cpu"),
        data.system.get("os"),
        data.system.get("kernel"),
        data.system.get("ram_gb"),
        data.metrics.get("fps_avg"),
        data.metrics.get("fps_min"),
        data.metrics.get("fps_1low"),
        data.metrics.get("fps_01low"),
        data.metrics.get("stutter_rating"),
        data.metrics.get("consistency_rating"),
        data.submitter.get("steam_id") if data.submitter else None,
        data.submitter.get("steam_name") if data.submitter else None,
        data.client_version,
    ))

    benchmark_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {
        "id": benchmark_id,
        "url": f"/benchmark/{benchmark_id}",
        "message": "Benchmark submitted successfully"
    }


@app.get("/api/v1/game/{steam_app_id}/benchmarks")
async def get_game_benchmarks(steam_app_id: int):
    """Get all benchmarks for a specific game."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM benchmarks
        WHERE steam_app_id = ?
        ORDER BY created_at DESC
    """, (steam_app_id,))

    rows = cursor.fetchall()
    conn.close()

    benchmarks = [dict(row) for row in rows]
    return {"count": len(benchmarks), "benchmarks": benchmarks}


@app.get("/api/v1/benchmarks")
async def get_all_benchmarks():
    """Get all benchmarks."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM benchmarks
        ORDER BY created_at DESC
        LIMIT 100
    """)

    rows = cursor.fetchall()
    conn.close()

    benchmarks = [dict(row) for row in rows]
    return {"count": len(benchmarks), "benchmarks": benchmarks}


@app.get("/api/v1/games")
async def get_games():
    """Get list of all games with benchmarks."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT steam_app_id, game_name, COUNT(*) as benchmark_count,
               AVG(fps_avg) as avg_fps
        FROM benchmarks
        GROUP BY steam_app_id
        ORDER BY benchmark_count DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    games = [dict(row) for row in rows]
    return {"count": len(games), "games": games}


@app.get("/benchmark/{benchmark_id}")
async def get_benchmark_detail(benchmark_id: int):
    """Get a specific benchmark."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM benchmarks WHERE id = ?", (benchmark_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Benchmark not found")

    return dict(row)


@app.get("/", response_class=HTMLResponse)
async def index():
    """Main page - serve static HTML."""
    static_file = Path("/opt/lgb/static/index.html")
    if static_file.exists():
        return HTMLResponse(content=static_file.read_text())
    else:
        return HTMLResponse(content="<h1>Frontend not found</h1>", status_code=404)


def generate_index_html(benchmarks: List[Dict]) -> str:
    """Generate the index HTML page."""

    # Group by game
    games = {}
    for b in benchmarks:
        game_name = b["game_name"]
        if game_name not in games:
            games[game_name] = []
        games[game_name].append(b)

    # Build cards HTML
    cards_html = ""
    for game_name, game_benchmarks in games.items():
        for b in game_benchmarks:
            fps_avg = b.get("fps_avg") or 0
            fps_1low = b.get("fps_1low") or 0

            # Color based on FPS
            if fps_avg >= 60:
                fps_color = "#00d26a"
            elif fps_avg >= 30:
                fps_color = "#ffc107"
            else:
                fps_color = "#ff5252"

            cards_html += f'''
            <div class="card" data-game="{game_name}" data-gpu="{b.get('gpu', '')}"
                 data-res="{b.get('resolution', '')}" data-os="{b.get('os', '')}">
                <div class="card-header">
                    <h3>{game_name}</h3>
                    <span class="resolution">{b.get('resolution', 'Unknown')}</span>
                </div>
                <div class="card-body">
                    <div class="fps-display" style="color: {fps_color}">
                        <span class="fps-value">{fps_avg:.0f}</span>
                        <span class="fps-label">AVG FPS</span>
                    </div>
                    <div class="metrics">
                        <div class="metric">
                            <span class="label">1% Low</span>
                            <span class="value">{fps_1low:.0f}</span>
                        </div>
                        <div class="metric">
                            <span class="label">GPU</span>
                            <span class="value">{b.get('gpu', 'Unknown')[:30]}</span>
                        </div>
                        <div class="metric">
                            <span class="label">OS</span>
                            <span class="value">{b.get('os', 'Linux')}</span>
                        </div>
                    </div>
                </div>
                <div class="card-footer">
                    <span class="submitter">{b.get('steam_name') or 'Anonymous'}</span>
                    <span class="date">{b.get('created_at', '')[:10]}</span>
                </div>
            </div>
            '''

    if not cards_html:
        cards_html = '''
        <div class="empty-state">
            <h2>No benchmarks yet</h2>
            <p>Be the first to submit a benchmark!</p>
            <p>Install lgb and run: <code>lgb record &lt;game&gt;</code></p>
        </div>
        '''

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Linux Game Benchmark</title>
    <style>
        :root {{
            --bg: #1a1a2e;
            --card: #25274d;
            --card-hover: #2d2f5a;
            --text: #eaeaea;
            --text-muted: #a0a0a0;
            --green: #00d26a;
            --yellow: #ffc107;
            --red: #ff5252;
            --blue: #4fc3f7;
            --purple: #b388ff;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, var(--bg) 0%, #16213e 100%);
            color: var(--text);
            min-height: 100vh;
            padding: 30px 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}

        header {{
            text-align: center;
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        header h1 {{
            font-size: 2.5rem;
            margin-bottom: 10px;
            background: linear-gradient(90deg, var(--blue), var(--purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        header .subtitle {{ color: var(--text-muted); font-size: 1.1rem; }}

        .stats {{
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-bottom: 30px;
        }}
        .stat {{
            text-align: center;
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: bold;
            color: var(--blue);
        }}
        .stat-label {{
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 20px;
        }}

        .card {{
            background: var(--card);
            border-radius: 16px;
            padding: 20px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        .card-header h3 {{
            font-size: 1.1rem;
            color: var(--text);
        }}
        .resolution {{
            background: rgba(79, 195, 247, 0.2);
            color: var(--blue);
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
        }}

        .fps-display {{
            text-align: center;
            margin: 20px 0;
        }}
        .fps-value {{
            font-size: 3rem;
            font-weight: bold;
        }}
        .fps-label {{
            display: block;
            color: var(--text-muted);
            font-size: 0.9rem;
        }}

        .metrics {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 15px;
        }}
        .metric {{
            text-align: center;
        }}
        .metric .label {{
            display: block;
            color: var(--text-muted);
            font-size: 0.75rem;
            margin-bottom: 3px;
        }}
        .metric .value {{
            color: var(--text);
            font-size: 0.85rem;
        }}

        .card-footer {{
            display: flex;
            justify-content: space-between;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid rgba(255,255,255,0.1);
            color: var(--text-muted);
            font-size: 0.8rem;
        }}

        .empty-state {{
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }}
        .empty-state h2 {{
            color: var(--text);
            margin-bottom: 10px;
        }}
        .empty-state code {{
            background: var(--card);
            padding: 5px 10px;
            border-radius: 5px;
            color: var(--blue);
        }}

        footer {{
            text-align: center;
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
            color: var(--text-muted);
        }}
        footer a {{
            color: var(--blue);
            text-decoration: none;
        }}
        footer a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Linux Game Benchmark</h1>
            <p class="subtitle">Community-driven gaming performance database for Linux</p>
        </header>

        <div class="stats">
            <div class="stat">
                <div class="stat-value">{len(benchmarks)}</div>
                <div class="stat-label">Benchmarks</div>
            </div>
            <div class="stat">
                <div class="stat-value">{len(games)}</div>
                <div class="stat-label">Games</div>
            </div>
        </div>

        <div class="cards">
            {cards_html}
        </div>

        <footer>
            Linux Game Benchmark &bull;
            <a href="https://github.com/taaderbe/linuxgamebench">GitHub</a>
        </footer>
    </div>
</body>
</html>'''

    return html


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
