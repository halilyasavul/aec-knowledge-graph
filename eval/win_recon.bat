@echo off
REM Reconnaissance for the Claude Code eval run: environment, Docker/Neo4j state, Claude Code CLI.
REM Writes eval\runs\_recon.log. Double-click to run.
cd /d "%~dp0.."
set LOG=eval\runs\_recon.log
echo === recon %DATE% %TIME% === > %LOG%
echo [cwd] %CD% >> %LOG%
echo [python] >> %LOG%
where python >> %LOG% 2>&1
python --version >> %LOG% 2>&1
python -c "import sys; print(sys.executable)" >> %LOG% 2>&1
python -c "import ifcopenshell, ifctester, neo4j, pydantic, lxml; print('core deps ok', ifcopenshell.version)" >> %LOG% 2>&1
python -c "import mcp; print('mcp ok')" >> %LOG% 2>&1
python -c "from google import genai; print('genai ok')" >> %LOG% 2>&1
echo [neo4j reachability] >> %LOG%
python -c "import neo4j; from dotenv import dotenv_values; v=dotenv_values('.env'); uri=v['NEO4J_URI']; print('env uri:', uri[:12]+'...'+uri[-22:]); d=neo4j.GraphDatabase.driver(uri, auth=(v['NEO4J_USER'], v['NEO4J_PASSWORD']), connection_timeout=20); s=d.session(); print('ENV-URI OK', dict(s.run('MATCH (c:Class) RETURN count(c) AS classes').single()))" >> %LOG% 2>&1
echo [claude] >> %LOG%
where claude >> %LOG% 2>&1
call claude --version >> %LOG% 2>&1
echo [docker] >> %LOG%
where docker >> %LOG% 2>&1
docker info >nul 2>&1
if errorlevel 1 (
  echo docker daemon not running; starting Docker Desktop >> %LOG%
  start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  set /a N=0
  :waitdocker
  timeout /t 5 /nobreak >nul
  set /a N+=1
  docker info >nul 2>&1
  if errorlevel 1 (
    if %N% LSS 36 goto waitdocker
    echo docker daemon did not come up in 180 s >> %LOG%
  ) else (
    echo docker daemon up after %N% x 5 s >> %LOG%
  )
) else (
  echo docker daemon already running >> %LOG%
)
python -c "import neo4j; d=neo4j.GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j','password123'), connection_timeout=5); s=d.session(); print('LOCAL OK', dict(s.run('MATCH (c:Class) RETURN count(c) AS classes').single()))" >> %LOG% 2>&1
echo [containers] >> %LOG%
docker ps -a --format "{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}" >> %LOG% 2>&1
echo [volumes] >> %LOG%
docker volume ls --format "{{.Name}}" >> %LOG% 2>&1
echo === done %TIME% === >> %LOG%
