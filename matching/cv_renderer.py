"""
cv_renderer.py — Renders a structured CV (JSON) into a polished .docx file.

Usage:
    from matching.cv_renderer import render_cv_to_docx
    render_cv_to_docx(tailored_cv_dict, output_path="cv/tailored/output.docx")

Internally this writes a temporary Node.js script using the `docx` library
and executes it via subprocess, since docx generation happens in JS per
the docx skill's recommended approach.
"""

import os
import json
import subprocess
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def _global_node_modules() -> str | None:
    """
    Returns the path to the global npm node_modules dir so Node can resolve
    a globally-installed `docx` package. Globally-installed modules are NOT
    on Node's default resolution path, so without this `require('docx')`
    fails even when `npm install -g docx` has been run.
    """
    try:
        result = subprocess.run(
            ["npm", "root", "-g"],
            capture_output=True, text=True, timeout=15, shell=(os.name == "nt")
        )
        path = result.stdout.strip()
        return path if path and Path(path).exists() else None
    except Exception:
        return None

NODE_TEMPLATE = r"""
const { Document, Packer, Paragraph, TextRun, AlignmentType, LevelFormat,
        HeadingLevel, BorderStyle } = require('docx');
const fs = require('fs');

const cv = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));

function bulletPara(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text, size: 21 })],
    spacing: { after: 60 }
  });
}

function sectionHeading(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, bold: true })],
    spacing: { before: 240, after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "444444", space: 1 } }
  });
}

const children = [];

// Name
children.push(new Paragraph({
  children: [new TextRun({ text: cv.name || "", bold: true, size: 32 })],
  spacing: { after: 40 }
}));

// Contact line
const contact = cv.contact || {};
const contactParts = [contact.email, contact.phone, contact.location, contact.linkedin, contact.github]
  .filter(Boolean).join("  |  ");
children.push(new Paragraph({
  children: [new TextRun({ text: contactParts, size: 18, color: "555555" })],
  spacing: { after: 200 }
}));

// Summary
if (cv.summary) {
  children.push(sectionHeading("Summary"));
  children.push(new Paragraph({
    children: [new TextRun({ text: cv.summary, size: 21 })],
    spacing: { after: 160 }
  }));
}

// Skills
if (cv.skills && cv.skills.length) {
  children.push(sectionHeading("Skills"));
  children.push(new Paragraph({
    children: [new TextRun({ text: cv.skills.join("  ·  "), size: 21 })],
    spacing: { after: 160 }
  }));
}

// Experience
if (cv.experience && cv.experience.length) {
  children.push(sectionHeading("Experience"));
  cv.experience.forEach(job => {
    children.push(new Paragraph({
      children: [
        new TextRun({ text: `${job.title || ""} — ${job.company || ""}`, bold: true, size: 22 }),
      ],
      spacing: { before: 120, after: 20 }
    }));
    if (job.dates) {
      children.push(new Paragraph({
        children: [new TextRun({ text: job.dates, italics: true, size: 19, color: "666666" })],
        spacing: { after: 60 }
      }));
    }
    (job.bullets || []).forEach(b => children.push(bulletPara(b)));
  });
}

// Projects
if (cv.projects && cv.projects.length) {
  children.push(sectionHeading("Projects"));
  cv.projects.forEach(proj => {
    children.push(new Paragraph({
      children: [new TextRun({ text: proj.name || "", bold: true, size: 22 })],
      spacing: { before: 120, after: 20 }
    }));
    if (proj.description) {
      children.push(new Paragraph({
        children: [new TextRun({ text: proj.description, size: 20, italics: true })],
        spacing: { after: 60 }
      }));
    }
    (proj.bullets || []).forEach(b => children.push(bulletPara(b)));
  });
}

// Education
if (cv.education && cv.education.length) {
  children.push(sectionHeading("Education"));
  cv.education.forEach(ed => {
    children.push(new Paragraph({
      children: [new TextRun({ text: `${ed.degree || ""} — ${ed.institution || ""}`, bold: true, size: 21 })],
      spacing: { before: 80, after: 20 }
    }));
    if (ed.dates) {
      children.push(new Paragraph({
        children: [new TextRun({ text: ed.dates, italics: true, size: 19, color: "666666" })],
        spacing: { after: 100 }
      }));
    }
  });
}

const doc = new Document({
  styles: { default: { document: { run: { font: "Calibri", size: 21 } } } },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 200 } } } }]
    }]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 800, right: 900, bottom: 800, left: 900 }
      }
    },
    children
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(process.argv[3], buffer);
  console.log("OK");
});
"""


def render_cv_to_docx(cv_data: dict, output_path: str) -> Path:
    """
    Renders a structured CV dict to a .docx file at output_path.
    Requires `npm install -g docx` to have been run already.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = output_path.parent
    script_path = tmp_dir / "_render_cv.js"
    data_path = tmp_dir / "_cv_data_tmp.json"

    script_path.write_text(NODE_TEMPLATE)
    data_path.write_text(json.dumps(cv_data))

    # Make globally-installed `docx` resolvable by Node via NODE_PATH.
    env = os.environ.copy()
    global_modules = _global_node_modules()
    if global_modules:
        existing = env.get("NODE_PATH", "")
        env["NODE_PATH"] = (
            global_modules + (os.pathsep + existing if existing else "")
        )

    try:
        result = subprocess.run(
            ["node", str(script_path), str(data_path), str(output_path)],
            capture_output=True, text=True, timeout=30, env=env
        )
        if result.returncode != 0:
            hint = ""
            if "Cannot find module 'docx'" in (result.stderr or ""):
                hint = (
                    " — the 'docx' npm package isn't resolvable. "
                    "Run `npm install -g docx` (already done?) and ensure Node "
                    "can find global modules."
                )
            raise RuntimeError(f"docx render failed{hint}: {result.stderr.strip()}")
    finally:
        script_path.unlink(missing_ok=True)
        data_path.unlink(missing_ok=True)

    return output_path
