from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import deps
import app.api.v1.endpoints.agent_tasks as agent_tasks_endpoint
from app.api.v1.endpoints.agent_tasks import router as agent_tasks_router
from app.db.base import Base
from app.models.agent_task import AgentEvent, AgentEventType, AgentTask, AgentTaskStatus
from app.models.audit_session import AuditSession
from app.models.project import Project
from app.models.user import User


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(agent_tasks_router, prefix='/api/v1/agent-tasks')
    return app


@pytest.mark.asyncio
async def test_agent_task_routes_include_runtime_session_id():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = User(
            id='user-1',
            email='owner@example.com',
            hashed_password='not-a-real-hash',
            full_name='Owner',
            is_active=True,
        )
        project = Project(
            id='project-1',
            name='Demo Project',
            owner_id='user-1',
            source_type='repository',
        )
        task = AgentTask(
            id='task-1',
            project_id='project-1',
            created_by='user-1',
            name='Audit demo',
            status=AgentTaskStatus.RUNNING,
            current_phase='analysis',
            created_at=datetime.now(timezone.utc),
        )
        session = AuditSession(
            id='session-1',
            project_id='project-1',
            task_id='task-1',
            runtime_stack='runtime',
            state='running',
        )
        db.add_all([user, project, task, session])
        await db.commit()

    app = build_test_app()

    async def override_get_db():
        async with session_factory() as db:
            yield db

    async def override_get_current_user():
        return SimpleNamespace(id='user-1', is_active=True)

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        list_response = await client.get('/api/v1/agent-tasks/')
        detail_response = await client.get('/api/v1/agent-tasks/task-1')

    await engine.dispose()

    assert list_response.status_code == 200
    assert list_response.json()[0]['runtime_session_id'] == 'session-1'

    assert detail_response.status_code == 200
    assert detail_response.json()['runtime_session_id'] == 'session-1'


@pytest.mark.asyncio
async def test_create_agent_task_persists_runtime_stack_in_agent_config(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = User(
            id='user-1',
            email='owner@example.com',
            hashed_password='not-a-real-hash',
            full_name='Owner',
            is_active=True,
        )
        project = Project(
            id='project-1',
            name='Demo Project',
            owner_id='user-1',
            source_type='repository',
        )
        db.add_all([user, project])
        await db.commit()

    async def fake_execute_agent_task(task_id: str):
        return None

    monkeypatch.setattr(agent_tasks_endpoint, '_execute_agent_task', fake_execute_agent_task)

    app = build_test_app()

    async def override_get_db():
        async with session_factory() as db:
            yield db

    async def override_get_current_user():
        return SimpleNamespace(id='user-1', is_active=True)

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        response = await client.post(
            '/api/v1/agent-tasks/',
            json={
                'project_id': 'project-1',
                'name': 'Runtime audit',
                'finding_runtime_stack': 'runtime',
            },
        )

    async with session_factory() as db:
        task = await db.get(AgentTask, response.json()['id'])

    await engine.dispose()

    assert response.status_code == 200
    assert task is not None
    assert task.agent_config == {'finding_runtime_stack': 'runtime'}


@pytest.mark.asyncio
async def test_agent_task_routes_include_resolved_runtime_stack():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = User(
            id='user-1',
            email='owner@example.com',
            hashed_password='not-a-real-hash',
            full_name='Owner',
            is_active=True,
        )
        project = Project(
            id='project-1',
            name='Demo Project',
            owner_id='user-1',
            source_type='repository',
        )
        task = AgentTask(
            id='task-1',
            project_id='project-1',
            created_by='user-1',
            name='Audit demo',
            status=AgentTaskStatus.RUNNING,
            current_phase='analysis',
            created_at=datetime.now(timezone.utc),
            agent_config={'finding_runtime_stack': 'runtime'},
        )
        db.add_all([user, project, task])
        await db.commit()

    app = build_test_app()

    async def override_get_db():
        async with session_factory() as db:
            yield db

    async def override_get_current_user():
        return SimpleNamespace(id='user-1', is_active=True)

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        list_response = await client.get('/api/v1/agent-tasks/')
        detail_response = await client.get('/api/v1/agent-tasks/task-1')

    await engine.dispose()

    assert list_response.status_code == 200
    assert list_response.json()[0]['finding_runtime_stack'] == 'runtime'
    assert detail_response.status_code == 200
    assert detail_response.json()['finding_runtime_stack'] == 'runtime'


@pytest.mark.asyncio
async def test_create_agent_task_uses_default_runtime_stack_from_settings(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = User(
            id='user-1',
            email='owner@example.com',
            hashed_password='not-a-real-hash',
            full_name='Owner',
            is_active=True,
        )
        project = Project(
            id='project-1',
            name='Demo Project',
            owner_id='user-1',
            source_type='repository',
        )
        db.add_all([user, project])
        await db.commit()

    async def fake_execute_agent_task(task_id: str):
        return None

    monkeypatch.setattr(agent_tasks_endpoint, '_execute_agent_task', fake_execute_agent_task)
    monkeypatch.setattr(agent_tasks_endpoint.settings, 'FINDING_RUNTIME_STACK_DEFAULT', 'runtime', raising=False)

    app = build_test_app()

    async def override_get_db():
        async with session_factory() as db:
            yield db

    async def override_get_current_user():
        return SimpleNamespace(id='user-1', is_active=True)

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        response = await client.post(
            '/api/v1/agent-tasks/',
            json={
                'project_id': 'project-1',
                'name': 'Default runtime audit',
            },
        )

    async with session_factory() as db:
        task = await db.get(AgentTask, response.json()['id'])

    await engine.dispose()

    assert response.status_code == 200
    assert task is not None
    assert task.agent_config == {'finding_runtime_stack': 'runtime'}

@pytest.mark.asyncio
async def test_agent_task_events_list_returns_history_for_activity_log():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        user = User(
            id='user-1',
            email='owner@example.com',
            hashed_password='not-a-real-hash',
            full_name='Owner',
            is_active=True,
        )
        project = Project(
            id='project-1',
            name='Demo Project',
            owner_id='user-1',
            source_type='repository',
        )
        task = AgentTask(
            id='task-1',
            project_id='project-1',
            created_by='user-1',
            name='Audit demo',
            status=AgentTaskStatus.RUNNING,
            current_phase='analysis',
            created_at=datetime.now(timezone.utc),
        )
        event = AgentEvent(
            id='event-1',
            task_id='task-1',
            event_type=AgentEventType.THINKING,
            sequence=1,
            phase='analysis',
            message='thinking...',
            created_at=datetime.now(timezone.utc),
        )
        db.add_all([user, project, task, event])
        await db.commit()

    app = build_test_app()

    async def override_get_db():
        async with session_factory() as db:
            yield db

    async def override_get_current_user():
        return SimpleNamespace(id='user-1', is_active=True)

    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        response = await client.get('/api/v1/agent-tasks/task-1/events/list')

    await engine.dispose()

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]['task_id'] == 'task-1'
    assert payload[0]['event_type'] == AgentEventType.THINKING
    assert payload[0]['timestamp']
    assert payload[0]['created_at']