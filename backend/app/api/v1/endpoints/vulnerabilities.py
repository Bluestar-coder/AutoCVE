from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api import deps
from app.db.session import get_db
from app.models.managed_vulnerability import ManagedVulnerability, ManagedVulnerabilityReport
from app.models.project import Project
from app.models.user import User
from app.schemas.managed_vulnerability import (
    ManagedVulnerabilityDetailResponse,
    ManagedVulnerabilityListResponse,
    ManagedVulnerabilityReportResponse,
    ManagedVulnerabilityReportUpdate,
    ManagedVulnerabilityUpdate,
)

router = APIRouter()


async def _get_owned_vulnerability(
    db: AsyncSession,
    *,
    vulnerability_id: str,
    owner_id: str,
) -> ManagedVulnerability:
    result = await db.execute(
        select(ManagedVulnerability)
        .join(Project, Project.id == ManagedVulnerability.project_id)
        .options(selectinload(ManagedVulnerability.reports))
        .where(ManagedVulnerability.id == vulnerability_id)
        .where(Project.owner_id == owner_id)
    )
    vulnerability = result.scalars().first()
    if vulnerability is None:
        raise HTTPException(status_code=404, detail='Vulnerability not found')
    return vulnerability


async def _get_owned_report(
    db: AsyncSession,
    *,
    vulnerability_id: str,
    report_kind: str,
    owner_id: str,
) -> tuple[ManagedVulnerability, ManagedVulnerabilityReport]:
    vulnerability = await _get_owned_vulnerability(db, vulnerability_id=vulnerability_id, owner_id=owner_id)
    report = next((item for item in vulnerability.reports if item.report_kind == report_kind), None)
    if report is None:
        raise HTTPException(status_code=404, detail='Report not found')
    return vulnerability, report


@router.get('', response_model=list[ManagedVulnerabilityListResponse])
async def list_vulnerabilities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
    project_name: Optional[str] = Query(None),
    version_label: Optional[str] = Query(None),
    project_link: Optional[str] = Query(None),
    repository_url_snapshot: Optional[str] = Query(None),
    vulnerability_name: Optional[str] = Query(None),
    vulnerability_type: Optional[str] = Query(None),
    human_review_result: Optional[str] = Query(None),
    cve_request_status: Optional[str] = Query(None),
    cve_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    query = (
        select(ManagedVulnerability)
        .join(Project, Project.id == ManagedVulnerability.project_id)
        .where(Project.owner_id == current_user.id)
        .order_by(ManagedVulnerability.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    if project_name:
        query = query.where(ManagedVulnerability.project_name.ilike(f'%{project_name}%'))
    if version_label:
        query = query.where(ManagedVulnerability.version_label == version_label)
    effective_project_link = project_link or repository_url_snapshot
    if effective_project_link:
        query = query.where(ManagedVulnerability.repository_url_snapshot == effective_project_link)
    if vulnerability_name:
        query = query.where(ManagedVulnerability.vulnerability_name.ilike(f'%{vulnerability_name}%'))
    if vulnerability_type:
        query = query.where(ManagedVulnerability.vulnerability_type == vulnerability_type)
    if human_review_result:
        query = query.where(ManagedVulnerability.human_review_result == human_review_result)
    if cve_request_status:
        query = query.where(ManagedVulnerability.cve_request_status == cve_request_status)
    if cve_id:
        query = query.where(ManagedVulnerability.cve_id.ilike(f'%{cve_id}%'))

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get('/{vulnerability_id}', response_model=ManagedVulnerabilityDetailResponse)
async def get_vulnerability(
    vulnerability_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    return await _get_owned_vulnerability(db, vulnerability_id=vulnerability_id, owner_id=current_user.id)


@router.patch('/{vulnerability_id}', response_model=ManagedVulnerabilityDetailResponse)
async def update_vulnerability(
    vulnerability_id: str,
    payload: ManagedVulnerabilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    vulnerability = await _get_owned_vulnerability(db, vulnerability_id=vulnerability_id, owner_id=current_user.id)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(vulnerability, key, value)
    vulnerability.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(vulnerability)
    return await _get_owned_vulnerability(db, vulnerability_id=vulnerability_id, owner_id=current_user.id)


@router.delete('/{vulnerability_id}', status_code=204)
async def delete_vulnerability(
    vulnerability_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    vulnerability = await _get_owned_vulnerability(db, vulnerability_id=vulnerability_id, owner_id=current_user.id)
    await db.delete(vulnerability)
    await db.commit()
    return Response(status_code=204)


@router.get('/{vulnerability_id}/reports', response_model=list[ManagedVulnerabilityReportResponse])
async def list_vulnerability_reports(
    vulnerability_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    vulnerability = await _get_owned_vulnerability(db, vulnerability_id=vulnerability_id, owner_id=current_user.id)
    return sorted(vulnerability.reports, key=lambda item: item.report_kind)


@router.get('/{vulnerability_id}/reports/{report_kind}', response_model=ManagedVulnerabilityReportResponse)
async def get_vulnerability_report(
    vulnerability_id: str,
    report_kind: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _, report = await _get_owned_report(
        db,
        vulnerability_id=vulnerability_id,
        report_kind=report_kind,
        owner_id=current_user.id,
    )
    return report


@router.patch('/{vulnerability_id}/reports/{report_kind}', response_model=ManagedVulnerabilityReportResponse)
async def update_vulnerability_report(
    vulnerability_id: str,
    report_kind: str,
    payload: ManagedVulnerabilityReportUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _, report = await _get_owned_report(
        db,
        vulnerability_id=vulnerability_id,
        report_kind=report_kind,
        owner_id=current_user.id,
    )
    report.markdown_content = payload.markdown_content
    report.source_type = payload.source_type or 'manual_edit'
    report.generation_status = 'completed'
    report.last_edited_at = datetime.now(timezone.utc)
    report.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(report)
    return report


@router.get('/{vulnerability_id}/reports/{report_kind}/export')
async def export_vulnerability_report(
    vulnerability_id: str,
    report_kind: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _, report = await _get_owned_report(
        db,
        vulnerability_id=vulnerability_id,
        report_kind=report_kind,
        owner_id=current_user.id,
    )
    return PlainTextResponse(report.markdown_content, media_type='text/markdown; charset=utf-8')
