"""Messaging interfaces and implementations for Wappa framework."""

from wappa.domain.interfaces.messaging_interface import IMessenger

from .whatsapp.messenger.whatsapp_messenger import WhatsAppMessenger

__all__ = ["IMessenger", "WhatsAppMessenger"]
