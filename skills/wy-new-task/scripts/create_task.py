#!/usr/bin/env python3
"""
wy-new-task 스킬의 ID 생성 + 폴더 스캐폴드 + registry.md 삽입을 담당.

CLAUDE.md 의 워크스페이스 컨벤션 (registry.md, 02_analyses/, 03_tasks/) 을 따른다.

JSON 메타데이터를 stdout 으로 출력해서 SKILL.md 의 Claude 가 파싱한다.

사용법:
  create_task.py --type T --title "..." --slug "..." --project "..." \\
                 --goal "..." --local-root "..." --mode A
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

KST = timezone(timedelta(hours=9))


def kst_now() -> datetime:
    return datetime.now(KST)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--type", default="T", choices=["F", "T"], help="기본 T (테스크). F 는 historical 호환용.")
    p.add_argument("--title", required=True, help="과제 제목 (한글 자유 형식)")
    p.add_argument("--slug", required=True, help="영문 slug (lowercase + hyphen)")
    p.add_argument("--project", default="", help="01_projects/ 하위 프로젝트명. 빈 값이면 무관")
    p.add_argument("--goal", default="", help="한 줄 골")
    p.add_argument("--local-root", required=True, help="워크스페이스 루트 절대경로")
    p.add_argument("--mode", required=True, choices=["A", "C"])
    p.add_argument("--from-jira", default="", help="모드 C 에서만 — 원천 Jira 키")
    p.add_argument("--jira-description", default="", help="모드 C 에서 brief 에 박을 description")
    p.add_argument("--due-date", default="", help="목표일자 ISO YYYY-MM-DD")
    p.add_argument("--part", default="", help="파트(Jira component) 이름")
    return p.parse_args()


def validate_slug(slug: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        raise ValueError(f"slug 는 lowercase 영숫자+하이픈만 허용: {slug!r}")
    return slug


def base_dir_for_type(t: str) -> str:
    return "02_analyses/active" if t in ("F", "S") else "03_tasks/active"


def next_id(local_root: Path, type_letter: str, today: str) -> str:
    base_active = local_root / base_dir_for_type(type_letter)
    base_done = base_active.parent / "done"
    prefix = f"{type_letter}-{today}-"
    seen = set()
    for base in (base_active, base_done):
        if not base.exists():
            continue
        for child in base.iterdir():
            name = child.name
            if name.startswith(prefix):
                m = re.match(rf"{re.escape(prefix)}(\d{{3}})_", name)
                if m:
                    seen.add(int(m.group(1)))
    n = 1
    while n in seen:
        n += 1
    return f"{type_letter}-{today}-{n:03d}"


def write_template(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    path.write_text(content, encoding="utf-8")


BRIEF_TPL = """# Brief — {title}

> **타입**: {type_label}
> **프로젝트**: {project_label}
> **파트**: {part_label}
> **목표일자**: {due_date_label}
> **생성**: {created_at}
{jira_lines}

## WHAT
{title}

## WHY
(deep-interview 또는 사용자 입력으로 채울 것)

## 한 줄 골
{goal}
"""

ASK_TPL = """# 분석 질문 — {title}

> **타입**: {type_label}
> **프로젝트**: {project_label}
> **파트**: {part_label}
> **목표일자**: {due_date_label}
> **생성**: {created_at}
{jira_lines}

## 핵심 질문
(deep-interview 로 구체화)

## 가설
- (작성 예정)

## 한 줄 골
{goal}
"""

GOALS_TPL = """# Goals — {title}

## 핵심 목표
{goal}

## 수용 기준 (측정 가능)
- [ ] (deep-interview 로 채워질 항목)

## Non-Goals
- (작성 예정)

## 완료 정의
(작성 예정)
"""

PROGRESS_TPL = """# Progress — {title}

## 상태
**활성 페이즈**: 01 initial (in_progress)
**최종 갱신**: {created_at}

## 페이즈 진행도
- [ ] **01 initial** — 첫 페이즈 (in_progress)

## 다음 할 일
- deep-interview 진행 (brief.md / 01_ask.md 보강)
- goals.md 수용 기준 채우기

## 최근 핸드오프
- (없음)
"""

PHASE_INITIAL_TPL = """# Phase 01 — initial

**기간**: {created_at_date} ~ 진행 중
**상태**: in_progress
**목표**: {goal}

## 컨텍스트
신규 과제. brief.md / goals.md 가 채워지면 본격 페이즈로 분리.

## 체크리스트
- [ ] deep-interview 완료
- [ ] goals.md 수용 기준 확정
- [ ] 첫 실행 가능 단위 정의

## 세션 로그

### {created_at_date}
- 한 일: 과제 생성, 폴더 스캐폴드
- 발견한 이슈: 없음
- 다음 할 일: deep-interview

## 페이즈 종료 요약
<!-- 페이즈 종료 시 작성 -->
"""


def insert_registry_row(registry_path: Path, task_id: str, title: str, type_label_kr: str, task_dir_rel: str, today_iso: str) -> bool:
    """진행 중 테이블 마지막 행 직전에 새 행 삽입."""
    if not registry_path.exists():
        return False
    text = registry_path.read_text(encoding="utf-8")
    new_row = f"| {task_id} | {title} | {type_label_kr} | {task_dir_rel} | {today_iso} |"
    # 진행 중 테이블의 마지막 행 찾기 — "## 완료" 직전까지 표 행 누적
    lines = text.splitlines()
    out = []
    inserted = False
    in_active_table = False
    for i, line in enumerate(lines):
        if line.strip() == "## 진행 중":
            in_active_table = True
        elif line.strip() == "## 완료" and in_active_table and not inserted:
            # 직전 빈 줄이 있다면 그 위에 삽입
            j = len(out) - 1
            while j >= 0 and out[j].strip() == "":
                j -= 1
            out.insert(j + 1, new_row)
            inserted = True
            in_active_table = False
        out.append(line)
    if not inserted:
        # 테이블 못 찾으면 파일 끝에 append
        out.append(new_row)
    registry_path.write_text("\n".join(out) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return True


def main() -> int:
    args = parse_args()
    args.slug = validate_slug(args.slug)
    local_root = Path(args.local_root).expanduser().resolve()
    if not local_root.exists():
        print(f"ERROR: local_root 없음: {local_root}", file=sys.stderr)
        return 2

    now = kst_now()
    today_compact = now.strftime("%Y-%m%d")  # 2026-0429
    today_iso = now.strftime("%Y-%m-%d")
    created_at = now.strftime("%Y-%m-%d %H:%M KST")

    task_id = next_id(local_root, args.type, today_compact)
    folder_name = f"{task_id}_{args.slug}"
    base_rel = base_dir_for_type(args.type)
    task_dir = local_root / base_rel / folder_name
    task_dir_rel = f"{base_rel}/{folder_name}/"

    if task_dir.exists():
        print(f"ERROR: 이미 존재: {task_dir}", file=sys.stderr)
        return 3

    type_label = {"F": "분석 (Feature)", "T": "구현 (Task)"}[args.type]
    type_label_kr = "분석" if args.type == "F" else "구현"
    project_label = args.project if args.project else "(무관)"

    jira_lines = ""
    if args.from_jira:
        jira_lines = f"> **Jira (원천)**: {args.from_jira}"

    fmt = dict(
        title=args.title,
        type_label=type_label,
        project_label=project_label,
        part_label=args.part or "(없음)",
        due_date_label=args.due_date or "(미정)",
        created_at=created_at,
        created_at_date=today_iso,
        goal=args.goal or "(미정)",
        jira_lines=jira_lines,
    )

    files_created = []
    if args.type in ("F", "S"):
        write_template(task_dir / "01_ask.md", ASK_TPL.format(**fmt))
        files_created.append(str(task_dir / "01_ask.md"))
    else:
        write_template(task_dir / "brief.md", BRIEF_TPL.format(**fmt))
        files_created.append(str(task_dir / "brief.md"))

    write_template(task_dir / "goals.md", GOALS_TPL.format(**fmt))
    write_template(task_dir / "progress.md", PROGRESS_TPL.format(**fmt))
    write_template(task_dir / "phases" / "01_initial.md", PHASE_INITIAL_TPL.format(**fmt))
    (task_dir / "handoffs").mkdir(parents=True, exist_ok=True)
    files_created += [
        str(task_dir / "goals.md"),
        str(task_dir / "progress.md"),
        str(task_dir / "phases/01_initial.md"),
        str(task_dir / "handoffs/"),
    ]

    registry_path = local_root / "registry.md"
    registry_inserted = insert_registry_row(
        registry_path, task_id, args.title, type_label_kr, task_dir_rel, today_iso
    )

    project_registry_inserted = False
    if args.project:
        project_root = local_root / "01_projects" / args.project
        project_root.mkdir(parents=True, exist_ok=True)
        project_registry = project_root / "registry.md"
        if not project_registry.exists():
            project_registry.write_text(
                f"# {args.project} — registry\n\n## 진행 중\n\n| ID | 이름 | 유형 | 경로 | 마지막 업데이트 |\n|----|------|------|------|----------------|\n\n## 완료\n\n| ID | 이름 | 유형 | 경로 | 완료일 |\n|----|------|------|------|--------|\n",
                encoding="utf-8",
            )
        project_registry_inserted = insert_registry_row(
            project_registry, task_id, args.title, type_label_kr, task_dir_rel, today_iso
        )

    out = {
        "due_date": args.due_date,
        "part": args.part,
        "task_id": task_id,
        "task_dir": str(task_dir),
        "task_dir_rel": task_dir_rel,
        "type": args.type,
        "type_label": type_label,
        "title": args.title,
        "slug": args.slug,
        "project": args.project,
        "registry_inserted": registry_inserted,
        "project_registry_inserted": project_registry_inserted,
        "files_created": files_created,
        "created_at": created_at,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
