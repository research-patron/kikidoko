from __future__ import annotations

from typing import Tuple

import firebase_admin
from firebase_admin import credentials, firestore

from .models import EquipmentRecord


def get_client(project_id: str, credentials_path: str | None) -> firestore.Client:
    if not firebase_admin._apps:
        if credentials_path:
            cred = credentials.Certificate(credentials_path)
            firebase_admin.initialize_app(cred, {"projectId": project_id})
        else:
            firebase_admin.initialize_app(options={"projectId": project_id})
    return firestore.client()


def upsert_equipment(
    client: firestore.Client, record: EquipmentRecord
) -> Tuple[str, str]:
    data = record.to_firestore()
    collection = client.collection("equipment")

    if record.equipment_id:
        existing = (
            collection.where("equipment_id", "==", record.equipment_id)
            .limit(1)
            .stream()
        )
        doc = next(existing, None)
        if doc:
            doc.reference.set(data, merge=True)
            return doc.id, "updated"

    if record.dedupe_key:
        existing = (
            collection.where("dedupe_key", "==", record.dedupe_key).limit(1).stream()
        )
        doc = next(existing, None)
        if doc:
            doc.reference.set(data, merge=True)
            return doc.id, "updated"

    doc_ref = collection.document()
    if not record.equipment_id:
        data["equipment_id"] = doc_ref.id
    doc_ref.set(data)
    return doc_ref.id, "created"
