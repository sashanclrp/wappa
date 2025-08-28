"""
Contact Echo Logic

Handles contact message echoing with comprehensive metadata extraction
and contact information processing.
"""

from typing import Any, Dict

from wappa.domain.interfaces.messaging_interface import IMessenger

from ..constants import CONTACT_ECHO_ENABLED, CONTACT_METADATA_ENABLED


async def handle_contact_echo(webhook, user_id: str, messenger: IMessenger,
                              metadata_extractor) -> Dict[str, Any]:
    """
    Handle contact message echo with metadata and contact processing.
    
    Echoes the contact information and extracts comprehensive
    metadata about the contact data and message context.
    
    Args:
        webhook: IncomingMessageWebhook
        user_id: User identifier
        messenger: Messaging interface
        metadata_extractor: Metadata extraction utilities
        
    Returns:
        Dictionary with echo result
    """
    try:
        message = webhook.message
        message_id = message.message_id
        
        # Extract contact data (handles both contact and contacts)
        contact_data = None
        message_type = None
        contacts_list = []
        
        if hasattr(message, 'contacts') and message.contacts:
            contacts_list = message.contacts
            message_type = "contacts"
        elif hasattr(message, 'contact') and message.contact:
            contacts_list = [message.contact]
            message_type = "contact"
            
        if not contacts_list:
            return {
                "success": False,
                "error": "No contact data found in message",
                "handler": "contact_echo",
                "user_id": user_id
            }
        
        # Prepare echo result
        result = {
            "success": True,
            "handler": "contact_echo",
            "user_id": user_id,
            "message_type": message_type,
            "original_message_id": message_id,
            "contacts_count": len(contacts_list)
        }
        
        # Build contact echo response
        if CONTACT_ECHO_ENABLED:
            echo_text = f"👥 **Contact Echo** ({len(contacts_list)} contact{'s' if len(contacts_list) > 1 else ''})\n\n"
            
            for idx, contact in enumerate(contacts_list, 1):
                if len(contacts_list) > 1:
                    echo_text += f"**Contact {idx}:**\n"
                
                # Extract contact fields
                name = getattr(contact, 'name', {})
                if isinstance(name, dict):
                    formatted_name = name.get('formatted_name', '')
                    first_name = name.get('first_name', '')
                    last_name = name.get('last_name', '')
                else:
                    formatted_name = str(name) if name else ''
                    first_name = ''
                    last_name = ''
                
                phones = getattr(contact, 'phones', [])
                emails = getattr(contact, 'emails', [])
                org = getattr(contact, 'org', {})
                urls = getattr(contact, 'urls', [])
                
                # Build contact info
                if formatted_name:
                    echo_text += f"📛 **Name:** {formatted_name}\n"
                elif first_name or last_name:
                    echo_text += f"📛 **Name:** {first_name} {last_name}".strip() + "\n"
                
                if phones:
                    for phone in phones:
                        phone_num = phone.get('phone', '') if isinstance(phone, dict) else str(phone)
                        phone_type = phone.get('type', '') if isinstance(phone, dict) else ''
                        type_label = f" ({phone_type})" if phone_type else ""
                        echo_text += f"📞 **Phone{type_label}:** {phone_num}\n"
                
                if emails:
                    for email in emails:
                        email_addr = email.get('email', '') if isinstance(email, dict) else str(email)
                        email_type = email.get('type', '') if isinstance(email, dict) else ''
                        type_label = f" ({email_type})" if email_type else ""
                        echo_text += f"📧 **Email{type_label}:** {email_addr}\n"
                
                if isinstance(org, dict) and org:
                    company = org.get('company', '')
                    department = org.get('department', '')
                    title = org.get('title', '')
                    
                    if company:
                        echo_text += f"🏢 **Company:** {company}\n"
                    if department:
                        echo_text += f"🏛️ **Department:** {department}\n"
                    if title:
                        echo_text += f"💼 **Title:** {title}\n"
                
                if urls:
                    for url in urls:
                        url_addr = url.get('url', '') if isinstance(url, dict) else str(url)
                        url_type = url.get('type', '') if isinstance(url, dict) else ''
                        type_label = f" ({url_type})" if url_type else ""
                        echo_text += f"🔗 **URL{type_label}:** {url_addr}\n"
                
                if idx < len(contacts_list):
                    echo_text += "\n"
            
            echo_text += "✅ Contact information received and echoed back!"
            
            echo_result = await messenger.send_text(
                recipient=user_id,
                text=echo_text,
                reply_to_message_id=message_id
            )
            
            result.update({
                "echo_sent": echo_result.success if echo_result else False,
                "echo_message_id": echo_result.message_id if echo_result else None,
                "echo_text_length": len(echo_text),
                "echo_error": None if echo_result and echo_result.success else "Failed to send echo"
            })
        else:
            result["echo_sent"] = False
            result["echo_disabled"] = True
            
        # Extract and include metadata if enabled
        if CONTACT_METADATA_ENABLED:
            try:
                metadata = await metadata_extractor.extract_message_metadata(webhook)
                
                # Add contact-specific metadata
                contact_metadata = {
                    "contacts_count": len(contacts_list),
                    "contacts": []
                }
                
                for contact in contacts_list:
                    contact_info = {}
                    
                    # Extract name info
                    name = getattr(contact, 'name', {})
                    if isinstance(name, dict):
                        contact_info.update({
                            "formatted_name": name.get('formatted_name'),
                            "first_name": name.get('first_name'),
                            "last_name": name.get('last_name')
                        })
                    
                    # Extract phones
                    phones = getattr(contact, 'phones', [])
                    if phones:
                        contact_info["phones"] = [
                            phone.get('phone') if isinstance(phone, dict) else str(phone)
                            for phone in phones
                        ]
                    
                    # Extract emails
                    emails = getattr(contact, 'emails', [])
                    if emails:
                        contact_info["emails"] = [
                            email.get('email') if isinstance(email, dict) else str(email)
                            for email in emails
                        ]
                    
                    # Extract organization
                    org = getattr(contact, 'org', {})
                    if isinstance(org, dict) and org:
                        contact_info["organization"] = {
                            k: v for k, v in org.items() if v
                        }
                    
                    # Filter out None values and empty fields
                    contact_info = {k: v for k, v in contact_info.items() if v}
                    if contact_info:
                        contact_metadata["contacts"].append(contact_info)
                
                result.update({
                    "metadata_extracted": True,
                    "general_metadata": metadata,
                    "contact_metadata": contact_metadata
                })
                
                # Send metadata response
                metadata_response = await metadata_extractor.build_metadata_response(
                    metadata, message_type=message_type, media_metadata=contact_metadata
                )
                
                if metadata_response:
                    metadata_result = await messenger.send_text(
                        recipient=user_id,
                        text=metadata_response,
                        reply_to_message_id=message_id
                    )
                    
                    result["metadata_response_sent"] = metadata_result.success if metadata_result else False
                    
            except Exception as metadata_error:
                result.update({
                    "metadata_extracted": False,
                    "metadata_error": str(metadata_error)
                })
        else:
            result["metadata_extraction_disabled"] = True
            
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "handler": "contact_echo",
            "user_id": user_id
        }