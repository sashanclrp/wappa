"""
Response transformation utilities for WhatsApp API routes.

Provides common data transformation functions to eliminate duplication
across route handlers.
"""


def convert_body_parameters(
    body_parameters: list | None,
) -> list[dict[str, str]] | None:
    """Convert Pydantic body parameters to dict format for messenger.

    Extracts the common pattern of converting template body parameters
    from Pydantic models to the dict format expected by messenger methods.

    Args:
        body_parameters: List of TemplateParameter Pydantic models or None

    Returns:
        List of dicts with 'type' and 'text' keys, or None if input is None
    """
    if not body_parameters:
        return None

    return [{"type": param.type.value, "text": param.text} for param in body_parameters]


def convert_buttons_to_dict(buttons: list) -> list[dict[str, str]]:
    """Convert Pydantic button models to dict format for messenger.

    Args:
        buttons: List of ReplyButton Pydantic models

    Returns:
        List of dicts with 'id' and 'title' keys
    """
    return [{"id": btn.id, "title": btn.title} for btn in buttons]


def convert_list_sections_to_dict(sections: list) -> list[dict]:
    """Convert Pydantic list sections to dict format for messenger.

    Args:
        sections: List of ListSection Pydantic models

    Returns:
        List of section dicts with 'title' and 'rows' keys
    """
    result = []
    for section in sections:
        section_dict = {"title": section.title, "rows": []}
        for row in section.rows:
            row_dict = {"id": row.id, "title": row.title}
            if row.description:
                row_dict["description"] = row.description
            section_dict["rows"].append(row_dict)
        result.append(section_dict)
    return result


def convert_header_to_dict(header) -> dict[str, str] | None:
    """Convert InteractiveHeader Pydantic model to dict format.

    Args:
        header: InteractiveHeader Pydantic model or None

    Returns:
        Dict format expected by messenger, or None if no header
    """
    if not header:
        return None

    header_dict = {"type": header.type.value}

    if header.type.value == "text" and header.text:
        header_dict["text"] = header.text
    elif header.type.value == "image" and header.image:
        header_dict["image"] = header.image
    elif header.type.value == "video" and header.video:
        header_dict["video"] = header.video
    elif header.type.value == "document" and header.document:
        header_dict["document"] = header.document

    return header_dict
