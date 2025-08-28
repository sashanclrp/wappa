"""
State Management Logic

Provides utilities for state cleanup, validation, and maintenance operations.
Handles orphaned states, expired states, and state consistency validation.
"""

from typing import Any, Dict, List, Optional
import asyncio
from datetime import datetime, timedelta

from ..constants import (
    BUTTON_STATE_TTL_SECONDS, LIST_STATE_TTL_SECONDS, 
    STATE_TYPE_BUTTON, STATE_TYPE_LIST, STATE_CLEANUP_ENABLED
)


async def handle_state_cleanup(user_id: str, state_manager, cleanup_type: str = "expired") -> Dict[str, Any]:
    """
    Handle state cleanup operations for a specific user.
    
    Removes expired states and optionally cleans up orphaned interactive states.
    
    Args:
        user_id: User identifier
        state_manager: StateManager instance
        cleanup_type: Type of cleanup ('expired', 'all', 'button', 'list')
        
    Returns:
        Dictionary with cleanup result
    """
    try:
        if not STATE_CLEANUP_ENABLED:
            return {
                "success": True,
                "cleanup_disabled": True,
                "user_id": user_id,
                "cleanup_type": cleanup_type
            }
        
        cleanup_results = {
            "success": True,
            "user_id": user_id,
            "cleanup_type": cleanup_type,
            "states_removed": 0,
            "states_validated": 0,
            "cleanup_details": {}
        }
        
        # Get current states for the user
        current_states = {}
        
        try:
            button_state = await state_manager.get_user_state(user_id, STATE_TYPE_BUTTON)
            if button_state:
                current_states[STATE_TYPE_BUTTON] = button_state
        except Exception:
            pass
            
        try:
            list_state = await state_manager.get_user_state(user_id, STATE_TYPE_LIST)
            if list_state:
                current_states[STATE_TYPE_LIST] = list_state
        except Exception:
            pass
        
        # Process cleanup based on type
        if cleanup_type in ["expired", "all"]:
            # Clean up expired states
            for state_type, state in current_states.items():
                if state.is_expired():
                    try:
                        await state_manager.delete_user_state(user_id, state_type)
                        cleanup_results["states_removed"] += 1
                        cleanup_results["cleanup_details"][state_type] = "expired_removed"
                    except Exception as e:
                        cleanup_results["cleanup_details"][state_type] = f"removal_failed: {str(e)}"
                else:
                    cleanup_results["states_validated"] += 1
                    cleanup_results["cleanup_details"][state_type] = "valid_kept"
        
        elif cleanup_type == "button":
            # Clean up only button states
            if STATE_TYPE_BUTTON in current_states:
                try:
                    await state_manager.delete_user_state(user_id, STATE_TYPE_BUTTON)
                    cleanup_results["states_removed"] += 1
                    cleanup_results["cleanup_details"][STATE_TYPE_BUTTON] = "force_removed"
                except Exception as e:
                    cleanup_results["cleanup_details"][STATE_TYPE_BUTTON] = f"removal_failed: {str(e)}"
        
        elif cleanup_type == "list":
            # Clean up only list states
            if STATE_TYPE_LIST in current_states:
                try:
                    await state_manager.delete_user_state(user_id, STATE_TYPE_LIST)
                    cleanup_results["states_removed"] += 1
                    cleanup_results["cleanup_details"][STATE_TYPE_LIST] = "force_removed"
                except Exception as e:
                    cleanup_results["cleanup_details"][STATE_TYPE_LIST] = f"removal_failed: {str(e)}"
        
        elif cleanup_type == "all":
            # Force cleanup all states
            for state_type in [STATE_TYPE_BUTTON, STATE_TYPE_LIST]:
                if state_type in current_states:
                    try:
                        await state_manager.delete_user_state(user_id, state_type)
                        cleanup_results["states_removed"] += 1
                        cleanup_results["cleanup_details"][state_type] = "force_removed"
                    except Exception as e:
                        cleanup_results["cleanup_details"][state_type] = f"removal_failed: {str(e)}"
        
        return cleanup_results
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "user_id": user_id,
            "cleanup_type": cleanup_type,
            "handler": "state_cleanup"
        }


async def handle_state_validation(user_id: str, state_manager, validation_type: str = "all") -> Dict[str, Any]:
    """
    Validate user states for consistency and correctness.
    
    Checks state expiration, validates context data, and ensures state consistency.
    
    Args:
        user_id: User identifier
        state_manager: StateManager instance
        validation_type: Type of validation ('all', 'button', 'list', 'consistency')
        
    Returns:
        Dictionary with validation result
    """
    try:
        validation_results = {
            "success": True,
            "user_id": user_id,
            "validation_type": validation_type,
            "states_validated": 0,
            "validation_issues": [],
            "validation_details": {}
        }
        
        # Get current states for validation
        states_to_validate = {}
        
        if validation_type in ["all", "button"]:
            try:
                button_state = await state_manager.get_user_state(user_id, STATE_TYPE_BUTTON)
                if button_state:
                    states_to_validate[STATE_TYPE_BUTTON] = button_state
            except Exception as e:
                validation_results["validation_issues"].append(f"Failed to get button state: {str(e)}")
        
        if validation_type in ["all", "list"]:
            try:
                list_state = await state_manager.get_user_state(user_id, STATE_TYPE_LIST)
                if list_state:
                    states_to_validate[STATE_TYPE_LIST] = list_state
            except Exception as e:
                validation_results["validation_issues"].append(f"Failed to get list state: {str(e)}")
        
        # Validate each state
        for state_type, state in states_to_validate.items():
            validation_results["states_validated"] += 1
            state_issues = []
            
            # Check expiration
            if state.is_expired():
                state_issues.append("expired")
                validation_results["validation_issues"].append(f"{state_type} state is expired")
            
            # Check TTL consistency
            expected_ttl = BUTTON_STATE_TTL_SECONDS if state_type == STATE_TYPE_BUTTON else LIST_STATE_TTL_SECONDS
            time_remaining = state.time_remaining_seconds()
            
            if time_remaining > expected_ttl:
                state_issues.append("ttl_too_long")
                validation_results["validation_issues"].append(f"{state_type} state TTL is longer than expected")
            
            # Validate context data
            if not state.context:
                state_issues.append("empty_context")
                validation_results["validation_issues"].append(f"{state_type} state has empty context")
            else:
                # State-specific context validation
                if state_type == STATE_TYPE_BUTTON:
                    if "options" not in state.context:
                        state_issues.append("missing_button_options")
                        validation_results["validation_issues"].append("Button state missing options context")
                    elif not state.context["options"]:
                        state_issues.append("empty_button_options")
                        validation_results["validation_issues"].append("Button state has empty options")
                
                elif state_type == STATE_TYPE_LIST:
                    if "options" not in state.context:
                        state_issues.append("missing_list_options")
                        validation_results["validation_issues"].append("List state missing options context")
                    elif not state.context["options"]:
                        state_issues.append("empty_list_options")
                        validation_results["validation_issues"].append("List state has empty options")
            
            # Record state validation details
            validation_results["validation_details"][state_type] = {
                "is_valid": len(state_issues) == 0,
                "issues": state_issues,
                "time_remaining_seconds": time_remaining,
                "context_keys": list(state.context.keys()) if state.context else [],
                "created_at": state.created_at.isoformat() if hasattr(state, 'created_at') else None
            }
        
        # Consistency checks if validating all states
        if validation_type in ["all", "consistency"] and len(states_to_validate) > 1:
            # Check for conflicting states (user shouldn't have both button and list active)
            if STATE_TYPE_BUTTON in states_to_validate and STATE_TYPE_LIST in states_to_validate:
                button_state = states_to_validate[STATE_TYPE_BUTTON]
                list_state = states_to_validate[STATE_TYPE_LIST]
                
                if not button_state.is_expired() and not list_state.is_expired():
                    validation_results["validation_issues"].append("Multiple active interactive states detected")
                    validation_results["validation_details"]["consistency"] = {
                        "issue": "conflicting_states",
                        "description": "Both button and list states are active simultaneously"
                    }
        
        # Set overall success based on critical issues
        critical_issues = [issue for issue in validation_results["validation_issues"] 
                          if any(keyword in issue.lower() for keyword in ["failed", "error", "critical"])]
        
        if critical_issues:
            validation_results["success"] = False
            validation_results["critical_issues"] = critical_issues
        
        return validation_results
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "user_id": user_id,
            "validation_type": validation_type,
            "handler": "state_validation"
        }


async def handle_bulk_state_cleanup(state_manager, max_states: int = 100) -> Dict[str, Any]:
    """
    Perform bulk cleanup of expired states across all users.
    
    This is a maintenance operation that should be run periodically
    to clean up orphaned and expired states.
    
    Args:
        state_manager: StateManager instance
        max_states: Maximum number of states to process in one operation
        
    Returns:
        Dictionary with bulk cleanup result
    """
    try:
        # This would need to be implemented based on the Redis key patterns
        # used by the StateManager. For now, return a placeholder.
        
        return {
            "success": True,
            "handler": "bulk_state_cleanup",
            "operation": "not_implemented",
            "message": "Bulk cleanup requires Redis key scanning implementation",
            "max_states": max_states,
            "recommendation": "Implement Redis SCAN operations for production use"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "handler": "bulk_state_cleanup"
        }