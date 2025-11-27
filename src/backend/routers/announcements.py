"""
Announcements endpoints for the High School Management System API
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, field_validator, Field
from bson import ObjectId
from bson.errors import InvalidId

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    start_date: Optional[str] = None
    expiration_date: str
    created_by: str

    @field_validator('message')
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate message is not empty or whitespace-only"""
        stripped = v.strip()
        if not stripped:
            raise ValueError('Message cannot be empty or contain only whitespace')
        return stripped


class AnnouncementUpdate(BaseModel):
    message: Optional[str] = Field(default=None, min_length=1, max_length=500)
    start_date: Optional[str] = None
    expiration_date: Optional[str] = None

    @field_validator('message')
    @classmethod
    def validate_message(cls, v: Optional[str]) -> Optional[str]:
        """Validate message is not empty or whitespace-only when provided"""
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError('Message cannot be empty or contain only whitespace')
        return stripped


def verify_authenticated_user(username: str) -> Dict[str, Any]:
    """Verify that the user is authenticated"""
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")
    return teacher


@router.get("/active")
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get all active announcements (public endpoint)"""
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # Find announcements that are currently active
    announcements = list(announcements_collection.find({
        "expiration_date": {"$gte": current_date}
    }))
    
    # Filter by start_date if present
    active_announcements = []
    for announcement in announcements:
        # If no start_date or start_date is in the past/today, include it
        if not announcement.get("start_date") or announcement["start_date"] <= current_date:
            # Convert ObjectId to string for JSON serialization
            if "_id" in announcement:
                announcement["_id"] = str(announcement["_id"])
            active_announcements.append(announcement)
    
    return active_announcements


@router.get("/all")
def get_all_announcements(username: str) -> List[Dict[str, Any]]:
    """Get all announcements (requires authentication)"""
    verify_authenticated_user(username)
    
    announcements = list(announcements_collection.find({}))
    
    # Convert ObjectId to string for JSON serialization
    for announcement in announcements:
        if "_id" in announcement:
            announcement["_id"] = str(announcement["_id"])
    
    # Sort by creation date, most recent first
    announcements.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return announcements


@router.post("/")
def create_announcement(announcement: AnnouncementCreate) -> Dict[str, Any]:
    """Create a new announcement (requires authentication)"""
    verify_authenticated_user(announcement.created_by)
    
    # Validate expiration_date is in the future
    try:
        expiration_dt = datetime.strptime(announcement.expiration_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid expiration date format. Use YYYY-MM-DD.")
    current_dt = datetime.now()
    if expiration_dt.date() <= current_dt.date():
        raise HTTPException(status_code=400, detail="Expiration date must be at least tomorrow")
    
    # Validate start_date is before expiration_date if provided
    if announcement.start_date:
        try:
            start_dt = datetime.strptime(announcement.start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start date format. Use YYYY-MM-DD.")
        if start_dt.date() > expiration_dt.date():
            raise HTTPException(status_code=400, detail="Start date must not be after expiration date")
    
    announcement_data = {
        "message": announcement.message,
        "start_date": announcement.start_date,
        "expiration_date": announcement.expiration_date,
        "created_by": announcement.created_by,
        "created_at": datetime.now().isoformat()
    }
    
    result = announcements_collection.insert_one(announcement_data)
    announcement_data["_id"] = str(result.inserted_id)
    
    return announcement_data
@router.put("/{announcement_id}")
def update_announcement(announcement_id: str, announcement: AnnouncementUpdate, username: str) -> Dict[str, Any]:
    """Update an existing announcement (requires authentication)"""
    verify_authenticated_user(username)
    
    try:
        obj_id = ObjectId(announcement_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")
    
    # Check if announcement exists
    existing = announcements_collection.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    # Build update data
    update_data = {}
    if announcement.message is not None:
        update_data["message"] = announcement.message
    if announcement.start_date is not None:
        update_data["start_date"] = announcement.start_date
    if announcement.expiration_date is not None:
        update_data["expiration_date"] = announcement.expiration_date
    
    # Validate dates if being updated
    final_start = update_data.get("start_date", existing.get("start_date"))
    final_expiration = update_data.get("expiration_date", existing.get("expiration_date"))
    
    if final_start and final_expiration and final_start > final_expiration:
        raise HTTPException(status_code=400, detail="Start date must be before expiration date")
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    update_data["updated_at"] = datetime.now().isoformat()
    update_data["updated_by"] = username
    
    announcements_collection.update_one(
        {"_id": obj_id},
        {"$set": update_data}
    )
    
    updated = announcements_collection.find_one({"_id": obj_id})
    updated["_id"] = str(updated["_id"])
    
    return updated


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, username: str) -> Dict[str, str]:
    """Delete an announcement (requires authentication)"""
    verify_authenticated_user(username)
    
    try:
        obj_id = ObjectId(announcement_id)
    except InvalidId:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")
    
    result = announcements_collection.delete_one({"_id": obj_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    return {"message": "Announcement deleted successfully"}
