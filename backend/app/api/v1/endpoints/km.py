# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta, date
from typing import Optional
from app.api.v1.endpoints.auth import get_current_user
from app.db.database import get_db
from app.models.models import User, Employee

router = APIRouter()

@router.get("/my-km")
def get_my_km_entries(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    days: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kilometer-Eintraege des eingeloggten Mitarbeiters"""
    
    # Hole Employee wie in time_entries.py
    employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Mitarbeiter nicht gefunden")
    
    params = {"emp_id": employee.id}
    
    query_str = """
        SELECT
            k.id,
            k.date,
            o.name as object_name,
            k.distance_km,
            k.amount,
            k.is_billable,
            k.is_longest_trip
        FROM km_daily_entries k
        JOIN objects o ON o.id = k.object_id
        WHERE k.employee_id = :emp_id
    """
    
    if date_from and date_to:
        query_str += " AND k.date BETWEEN :date_from AND :date_to"
        params["date_from"] = date_from
        params["date_to"] = date_to
    elif days:
        date_from_calc = datetime.now().date() - timedelta(days=days)
        date_to_calc = datetime.now().date()
        query_str += " AND k.date BETWEEN :date_from AND :date_to"
        params["date_from"] = date_from_calc
        params["date_to"] = date_to_calc
    
    query_str += " ORDER BY k.date DESC"
    
    try:
        result = db.execute(text(query_str), params).fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Datenbankfehler: {str(e)}")
    
    entries = []
    for row in result:
        entry = {
            "id": row.id,
            "date": row.date.isoformat(), 
            "object_name": row.object_name,
            "distance_km": float(row.distance_km or 0),
            "amount": float(row.amount or 0),
            "is_billable": row.is_billable,
            "is_longest_trip": row.is_longest_trip
        }
        entries.append(entry)
    
    return entries
