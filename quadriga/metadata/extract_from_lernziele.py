"""Extract learning objectives with metadata from Lernziele.md files."""

from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Any
from .utils import get_repo_root, save_yaml_file, get_file_path, load_yaml_file

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# Default values for missing metadata
DEFAULT_COMPETENCY = "nicht anwendbar"
DEFAULT_BLOOMS = "nicht anwendbar"
DEFAULT_DATA_FLOW = "nicht anwendbar"


def parse_metadata_comment(comment: str) -> dict[str, str]:
    """
    Parse metadata from HTML comment.
    
    Format: <!-- competency: X | blooms: Y | data-flow: Z -->
    
    Args:
        comment: HTML comment string
    
    Returns:
        dict: Parsed metadata
    """
    metadata = {}
    
    # Remove HTML comment markers
    content = re.sub(r'<!--\s*|\s*-->', '', comment)
    
    # Split by pipe
    parts = content.split('|')
    
    for part in parts:
        part = part.strip()
        if ':' in part:
            key, value = part.split(':', 1)
            key = key.strip().lower().replace(' ', '-')
            value = value.strip()
            
            # Map keys to expected format
            if key == 'blooms':
                metadata['blooms-category'] = value
            elif key == 'competency':
                metadata['competency'] = value
            elif key == 'data-flow':
                metadata['data-flow'] = value
    
    return metadata


def validate_objective_metadata(
    objective_data: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """
    Validate and fill in missing metadata for a learning objective.
    
    Args:
        objective_data: Objective data dictionary
    
    Returns:
        tuple: (validated objective data, list of missing fields)
    """
    missing_fields = []
    
    # Check required fields
    if 'competency' not in objective_data or not objective_data['competency']:
        missing_fields.append('competency')
        objective_data['competency'] = DEFAULT_COMPETENCY
    
    if 'blooms-category' not in objective_data or not objective_data['blooms-category']:
        missing_fields.append('blooms-category')
        objective_data['blooms-category'] = DEFAULT_BLOOMS
    
    if 'data-flow' not in objective_data or not objective_data['data-flow']:
        missing_fields.append('data-flow')
        objective_data['data-flow'] = DEFAULT_DATA_FLOW
    
    return objective_data, missing_fields


def extract_admonition_blocks(
    content: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Extract all admonition blocks with learning objectives from Markdown content.
    
    Args:
        content: Markdown file content
    
    Returns:
        tuple: (extracted blocks, validation issues)
    """
    blocks = []
    validation_issues = []
    
    # Pattern to match admonition blocks with their content
    admonition_pattern = r'```\{admonition\}\s+(.+?)\n((?::[^\n]+\n)*)((?:(?!```).)+)```'
    
    matches = re.finditer(admonition_pattern, content, re.DOTALL | re.MULTILINE)
    
    for match in matches:
        title_line = match.group(1).strip()
        options_block = match.group(2).strip()
        body = match.group(3).strip()
        
        # Parse title - extract text and reference
        title_match = re.match(r'\[(.+?)\]\((.+?)\)(\s*\(\*(.+?)\*\))?', title_line)
        
        if not title_match:
            logger.warning("Could not parse admonition title: %s", title_line)
            continue
        
        section_title = title_match.group(1)
        section_ref = title_match.group(2)
        section_note = title_match.group(4) if title_match.group(4) else None
        
        # Look for START marker with chapter name in the body
        # Format: <!-- START: ChapterName -->
        chapter = None
        start_marker_match = re.search(r'<!--\s*START:\s*(.+?)\s*-->', body)
        
        if start_marker_match:
            # Extract chapter name directly from START marker
            chapter = start_marker_match.group(1).strip()
            
            # Remove START and END markers from body for processing
            body_cleaned = re.sub(r'<!--\s*START:\s*.+?\s*-->\s*', '', body)
            body_cleaned = re.sub(r'\s*<!--\s*END:\s*.+?\s*-->', '', body_cleaned)
        
        # Extract objectives from cleaned body
        objectives = []
        
        # Pattern: numbered list item followed by optional metadata comment
        objective_pattern = r'(\d+)\.\s+(.+?)(?:\n\s*<!--\s*(.+?)\s*-->)?(?=\n\d+\.|\n\n|$)'
        
        obj_matches = re.finditer(objective_pattern, body_cleaned, re.DOTALL)
        
        for obj_match in obj_matches:
            objective_text = obj_match.group(2).strip()
            metadata_comment = obj_match.group(3)
            
            objective_data = {
                'learning-objective': objective_text
            }
            
            # Parse metadata if present
            if metadata_comment:
                metadata = parse_metadata_comment(metadata_comment)
                objective_data.update(metadata)
            
            # Validate and fill in missing metadata
            objective_data, missing_fields = validate_objective_metadata(objective_data)
            
            # Track validation issues
            if missing_fields:
                validation_issues.append({
                    'section': section_title,
                    'objective': objective_text[:60],
                    'missing_fields': missing_fields
                })
            
            objectives.append(objective_data)
        
        if objectives:
            block_data = {
                'section-title': section_title,
                'section-reference': section_ref,
                'objectives': objectives
            }
            
            if section_note:
                block_data['section-note'] = section_note
            
            if chapter:
                block_data['chapter'] = chapter
            else:
                logger.warning(
                    "No chapter specified for section '%s'. "
                    "Add '<!-- START: ChapterName -->' at the beginning of the objectives.",
                    section_title
                )
            
            blocks.append(block_data)
            logger.info(
                "Extracted section '%s' with %d objectives (chapter: %s)",
                section_title,
                len(objectives),
                chapter or "unknown"
            )
    
    return blocks, validation_issues


def extract_from_lernziele_file(
    md_file_path: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Extract learning objectives from a Lernziele.md file.
    
    Args:
        md_file_path: Path to Lernziele.md
    
    Returns:
        tuple: (extracted sections, validation issues)
    """
    try:
        with md_file_path.open(encoding="utf-8") as f:
            content = f.read()
        
        blocks, issues = extract_admonition_blocks(content)
        
        logger.info(
            "Extracted %d admonition blocks from %s",
            len(blocks),
            md_file_path.name
        )
        
        if issues:
            logger.info(
                "Found %d objectives with missing metadata in %s",
                len(issues),
                md_file_path.name
            )
        
        return blocks, issues
        
    except FileNotFoundError:
        logger.error("File not found: %s", md_file_path)
        return [], []
    except Exception:
        logger.exception("Error reading file: %s", md_file_path)
        return [], []


def find_lernziele_files(repo_root: Path) -> list[Path]:
    """
    Find all Lernziele.md files in the repository.
    
    Args:
        repo_root: Repository root path
    
    Returns:
        list[Path]: List of Lernziele.md file paths
    """
    patterns = ["**/[Ll]ernziel*.md", "**/*learning*objective*.md"]
    files = []
    
    for pattern in patterns:
        found = list(repo_root.glob(pattern))
        # Exclude generated files and templates
        found = [f for f in found if not f.name.startswith('_') and not f.suffix == '.j2']
        files.extend(found)
    
    # Remove duplicates
    files = list(set(files))
    
    logger.info("Found %d Lernziele files", len(files))
    return files


def generate_validation_report(
    validation_issues: list[dict[str, Any]],
    output_path: Path | None = None
) -> str:
    """
    Generate a human-readable validation report.
    
    Args:
        validation_issues: List of validation issues
        output_path: Optional path to save the report
    
    Returns:
        str: Formatted report
    """
    if not validation_issues:
        report = "✅ All learning objectives have complete metadata!\n"
    else:
        report = f"⚠️ Found {len(validation_issues)} learning objectives with missing metadata:\n\n"
        
        for i, issue in enumerate(validation_issues, 1):
            report += f"{i}. Section: {issue['section']}\n"
            report += f"   Objective: {issue['objective']}...\n"
            report += f"   Missing: {', '.join(issue['missing_fields'])}\n\n"
        
        report += "\nTo fix: Add HTML comments after each objective:\n"
        report += "<!-- competency: X | blooms: Y | data-flow: Z -->\n"
    
    if output_path:
        with output_path.open("w", encoding="utf-8") as f:
            f.write(report)
        logger.info("Validation report saved to %s", output_path)
    
    return report


def merge_learning_objectives_into_metadata() -> bool:
    """
    Extract learning objectives from Markdown files and merge into metadata.yml.
    
    Returns:
        bool: True if successful
    """
    try:
        repo_root = get_repo_root()
        
        # Find all Lernziele.md files
        lernziele_files = find_lernziele_files(repo_root)
        
        if not lernziele_files:
            logger.warning("No Lernziele files found")
            return True
        
        # Extract all learning objectives
        all_sections = []
        all_validation_issues = []
        
        for md_file in lernziele_files:
            sections, issues = extract_from_lernziele_file(md_file)
            all_sections.extend(sections)
            all_validation_issues.extend(issues)
        
        # Generate validation report
        report_path = repo_root / "learning-objectives-validation.txt"
        
        if all_validation_issues:
            generate_validation_report(all_validation_issues, report_path)
            logger.warning(
                "Found %d objectives with missing metadata. "
                "See learning-objectives-validation.txt for details.",
                len(all_validation_issues)
            )
        else:
            logger.info("✅ All learning objectives have complete metadata")
            # DELETE the old validation report if it exists
            if report_path.exists():
                report_path.unlink()
                logger.info("Removed old validation report (no issues found)")
    
        if not all_sections:
            logger.warning("No learning objectives extracted")
            return True
        
        # Load existing metadata.yml
        metadata_path = get_file_path("metadata.yml", repo_root)
        metadata = load_yaml_file(metadata_path)
        
        if not metadata or not isinstance(metadata, dict):
            logger.error("Could not load metadata.yml")
            return False
        
        # Build a mapping of chapter name to objectives
        chapter_objectives = {}
        for section in all_sections:
            chapter = section.get('chapter')
            if chapter:
                if chapter not in chapter_objectives:
                    chapter_objectives[chapter] = []
                chapter_objectives[chapter].extend(section['objectives'])
        
        # Merge into metadata chapters
        if "chapters" in metadata:
            for chapter in metadata["chapters"]:
                chapter_title = chapter.get("title", "")
                
                if chapter_title in chapter_objectives:
                    objectives = chapter_objectives[chapter_title]
                    chapter["learning-objectives"] = objectives
        
        if save_yaml_file(metadata_path, metadata):
            logger.info("Successfully merged learning objectives into metadata.yml")
            return True
        else:
            logger.error("Failed to save updated metadata.yml")
            return False
        
    except Exception:
        logger.exception("Error merging learning objectives")
        return False


if __name__ == "__main__":
    # Extract and merge into metadata
    success = merge_learning_objectives_into_metadata()
    exit(0 if success else 1)