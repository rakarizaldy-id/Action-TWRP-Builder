#!/usr/bin/env python3
"""Map transient HTTP checkout failures to verified project paths."""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TRANSPORT = re.compile(
    r"HTTP\s+(?:429|5\d\d)|returned error:\s*(?:429|5\d\d)|"
    r"Connection reset by peer|remote end hung up unexpectedly",
    re.I,
)
FAILED = re.compile(
    r"Cannot\s+(?:checkout|fetch|initialize work tree for)\s+"
    r"(?P<name>[A-Za-z0-9_.+/-]+)",
    re.I,
)
SAFE = re.compile(r"[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*\Z")


def failed_projects(log: str, xml: str) -> list[str]:
    if not TRANSPORT.search(log):
        raise ValueError("not an identified transient upstream transport failure")
    projects = ET.fromstring(xml).findall("project")
    mapping = {}
    paths = []
    for project in projects:
        name = project.get("name")
        path = project.get("path") or name
        if not name or not path or not SAFE.fullmatch(name) or not SAFE.fullmatch(path):
            raise ValueError("invalid upstream project identity")
        paths.append(path)
        mapping[name] = path
        mapping[path] = path
    if len(projects) != 391 or len(set(paths)) != 391:
        raise ValueError("source manifest must contain 391 unique projects")
    names = [m.group("name") for m in FAILED.finditer(log)]
    for m in re.finditer(
        r"Failing repos \((?:checkout|network)\):\s*\n"
        r"((?:[ \t]*[A-Za-z0-9_.+/-]+[ \t]*\n)+)", log, re.I
    ):
        names.extend(x.strip() for x in m.group(1).splitlines())
    if not names:
        raise ValueError("upstream project failure not identifiable")
    unknown = sorted(set(names) - mapping.keys())
    if unknown:
        raise ValueError("not in pinned manifest: " + ", ".join(unknown))
    found = list(dict.fromkeys(mapping[name] for name in names))
    if len(found) > 8:
        raise ValueError("too many failed projects for bounded targeted recovery")
    return found


def self_test() -> None:
    projects = [
        '<project name="platform/project%s" path="project%s"/>' % (i, i)
        for i in range(389)
    ] + [
        '<project name="platform/external/libbpf" path="external/libbpf"/>',
        '<project name="platform/external/pandora/bt-test-interfaces" '
        'path="external/pandora/bt-test-interfaces"/>'
    ]
    xml = "<manifest>" + "".join(projects) + "</manifest>"
    one = ("error: RPC failed; HTTP 502 curl 22\n"
           "fatal: expected 'packfile'\n"
           "Cannot checkout platform/external/libbpf\n"
           "Failing repos (checkout):\nexternal/libbpf\n")
    two = ("error: RPC failed; HTTP 503 curl 22\n"
           "Cannot initialize work tree for "
           "platform/external/pandora/bt-test-interfaces\n")
    assert failed_projects(one, xml) == ["external/libbpf"]
    assert failed_projects(two, xml) == ["external/pandora/bt-test-interfaces"]
    for bad in (
        "Cannot checkout platform/external/libbpf",
        "HTTP 503\nCannot checkout unexpected/other",
        "HTTP 503\nfatal: expected 'packfile'",
    ):
        try:
            failed_projects(bad, xml)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe recovery was accepted: " + bad)
    print("PASS: transport failure whitelist, 391-project manifest, safe retry bounds")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 3:
        try:
            for project in failed_projects(
                Path(sys.argv[1]).read_text(errors="replace"),
                Path(sys.argv[2]).read_text(),
            ):
                print(project)
        except (ValueError, ET.ParseError) as exc:
            raise SystemExit("BLOCKED: " + str(exc))
    else:
        raise SystemExit("usage: extract_failed_sync_projects.py LOG MANIFEST | --self-test")
