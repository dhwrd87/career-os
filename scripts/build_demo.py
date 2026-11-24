#!/usr/bin/env python3
"""Build a fictional example through actual package workflows, outside source."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from careeros import experience
from careeros.core.io import read_json

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(ROOT/'tests/e2e'))
    from run_clean_room import run
    summary=run(args.output)
    for persona in ('early-career','career-changer','experienced-multi-role'):
        workspace=args.output/persona
        build=next((workspace/'state/resume-builds').glob('*/build.json'))
        record=read_json(build)
        experience.export_resume(workspace,record['build_id'])
        experience.cover_letter(workspace,record['opportunity_id'],record['build_id'])
        experience.interview(workspace,record['opportunity_id'],stage='TECHNICAL',timestamp='2026-10-02T12:00:00Z')
        packet=next((workspace/'state/application-packets').glob('*.json'))
        application=read_json(packet)['application_id']
        experience.record_event(workspace,application,{'event_type':'SUBMITTED','actor':'synthetic-human','occurred_at':'2026-10-02T15:00:00Z','human_confirmed':True})
        experience.follow_up(workspace,application,due_at='2026-10-09T12:00:00Z',channel='EMAIL')
        experience.analytics(workspace,window_end='2026-10-12T00:00:00Z',timestamp='2026-10-12T00:00:00Z')
        if persona=='career-changer':
            from build_learning_example import build as build_learning
            build_learning(workspace)
        experience.dashboard(workspace)
    print(json.dumps({'status':summary['status'],'workspaces':3,'synthetic_only':True,'external_actions':0}))

if __name__=='__main__':main()
