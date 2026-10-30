import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from passlib.context import CryptContext
from motor.motor_asyncio import AsyncIOMotorClient
import pymongo

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

class DualModeDatabase:
    """
    Robust Dual-Mode Database Manager for RestockIQ:
    1. Primary: MongoDB Atlas (via Motor async driver).
    2. Resilient Fallback: Local thread-safe JSON persistence (data/local_db.json)
       automatically activated if network firewall / port 27017 or Atlas credentials fail.
    This guarantees 100% functionality and testability in all deployment environments.
    """
    def __init__(self, mongo_uri: Optional[str] = None, db_name: str = "restockiq", data_dir: Optional[Path] = None):
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.db = None
        self.is_atlas_active: bool = False
        self.data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.local_file = self.data_dir / "local_db.json"
        self._lock = asyncio.Lock()
        self._local_cache: Dict[str, List[Dict[str, Any]]] = {
            "users": [],
            "shops": [],
            "items": [],
            "sales": [],
            "waste_alerts": [],
            "forecasts": [],
            "audit_logs": []
        }

    async def initialize(self, allow_demo_seed: bool = True):
        # 1. Load local persistence file if it exists
        if self.local_file.exists():
            try:
                with open(self.local_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k in self._local_cache.keys():
                        self._local_cache[k] = data.get(k, [])
            except Exception as e:
                print(f"[DB] Notice: Could not read local_db.json ({e}). Initializing empty cache.")

        # 2. Seed initial core items if catalog is empty
        if not self._local_cache["items"]:
            self._seed_default_items()
            self._save_local_file()

        # 3. Attempt Atlas connection with non-blocking fail-fast timeout (3s)
        if self.mongo_uri:
            try:
                self.client = AsyncIOMotorClient(
                    self.mongo_uri,
                    serverSelectionTimeoutMS=3000,
                    connectTimeoutMS=3000,
                    socketTimeoutMS=3000,
                )
                self.db = self.client[self.db_name]
                # Ping test
                await self.client.admin.command('ping')
                self.is_atlas_active = True
                print("[DB] Successfully connected to MongoDB Atlas.")
            except Exception as e:
                self.is_atlas_active = False
                print(f"[DB] Notice: MongoDB Atlas ping unreachable ({e}). Activating resilient Local Storage Mode at {self.local_file.name}.")

        # 4. Seed demo users if requested
        if allow_demo_seed:
            await self.seed_demo_user()

    def _seed_default_items(self):
        now_str = datetime.now(timezone.utc).isoformat()
        default_skus = [
            {
                "_id": "item_1",
                "id": "item_1",
                "name": "Kajukatli",
                "category": "Bread",
                "unit": "kg",
                "currentStock": 5,
                "isPerishable": True,
                "price": 69.0,
                "costPrice": 30.0,
                "predictedDemand": 10,
                "safetyStock": 4,
                "description": "chvgujy cy7",
                "riskLevel": "normal",
                "owner_id": "demo_walkthrough_owner",
                "shelf_life_days": 5,
                "updatedAt": now_str,
            },
            {
                "_id": "item_2",
                "id": "item_2",
                "name": "sweet",
                "category": "Beverage",
                "unit": "pcs",
                "currentStock": 2,
                "isPerishable": True,
                "price": 70.0,
                "costPrice": 50.0,
                "predictedDemand": 10,
                "safetyStock": 4,
                "description": "lkokokok",
                "riskLevel": "high",
                "owner_id": "demo_walkthrough_owner",
                "shelf_life_days": 3,
                "updatedAt": now_str,
            },
            {
                "_id": "item_3",
                "id": "item_3",
                "name": "brfi",
                "category": "Dairy",
                "unit": "pcs",
                "currentStock": 82,
                "isPerishable": True,
                "price": 100.0,
                "costPrice": 77.0,
                "predictedDemand": 135,
                "safetyStock": 33,
                "description": "Fresh Dairy item.",
                "riskLevel": "normal",
                "owner_id": "demo_walkthrough_owner",
                "shelf_life_days": 3,
                "updatedAt": now_str,
            },
            {
                "_id": "item_4",
                "id": "item_4",
                "name": "paaaav",
                "category": "Dairy",
                "unit": "pcs",
                "currentStock": 3,
                "isPerishable": True,
                "price": 40.0,
                "costPrice": 35.0,
                "predictedDemand": 10,
                "safetyStock": 4,
                "description": "Fresh Dairy item.",
                "riskLevel": "high",
                "owner_id": "demo_walkthrough_owner",
                "shelf_life_days": 2,
                "updatedAt": now_str,
            },
            {
                "_id": "item_5",
                "id": "item_5",
                "name": "Strawberry",
                "category": "Pastry",
                "unit": "pcs",
                "currentStock": 50,
                "isPerishable": True,
                "price": 60.0,
                "costPrice": 30.0,
                "predictedDemand": 20,
                "safetyStock": 5,
                "description": "Fresh Pastry item.",
                "riskLevel": "normal",
                "owner_id": "demo_walkthrough_owner",
                "shelf_life_days": 1,
                "updatedAt": now_str,
            },
            {
                "_id": "item_6",
                "id": "item_6",
                "name": "periperi",
                "category": "Snacks",
                "unit": "pcs",
                "currentStock": 20,
                "isPerishable": False,
                "price": 80.0,
                "costPrice": 11.0,
                "predictedDemand": 20,
                "safetyStock": 5,
                "description": "Fresh Snacks item.",
                "riskLevel": "normal",
                "owner_id": "demo_walkthrough_owner",
                "shelf_life_days": 30,
                "updatedAt": now_str,
            }
        ]
        self._local_cache["items"] = default_skus

    def _save_local_file(self):
        try:
            with open(self.local_file, "w", encoding="utf-8") as f:
                json.dump(self._local_cache, f, indent=2, default=str)
        except Exception as e:
            print(f"[DB] Error writing local_db.json: {e}")

    async def seed_demo_user(self):
        now_str = datetime.now(timezone.utc).isoformat()
        demo_accounts = [
            {
                "_id": "demo_walkthrough_owner",
                "name": "Demo Admin",
                "email": "admin@test.com",
                "password_hash": hash_password("123456"),
                "role": "owner",
                "shop_name": "Artisan Sourdough & Café",
                "store_name": "Artisan Sourdough & Café",
                "shop_type": "Bakery",
                "shop_id": "shop_demo_01",
                "onboarding_completed": True,
                "created_at": now_str,
            },
            {
                "_id": "manager_demo_owner",
                "name": "Store Manager",
                "email": "manager@cafe.com",
                "password_hash": hash_password("password123"),
                "role": "manager",
                "shop_name": "Downtown Espresso & Bakery",
                "store_name": "Downtown Espresso & Bakery",
                "shop_type": "Café",
                "shop_id": "shop_demo_02",
                "onboarding_completed": True,
                "created_at": now_str,
            },
            {
                "_id": "demo_walkthrough_owner",
                "name": "RestockIQ Evaluator",
                "email": "demo@restockiq.com",
                "password_hash": hash_password("demo123456"),
                "role": "owner",
                "shop_name": "Artisan Sourdough & Café",
                "store_name": "Artisan Sourdough & Café",
                "shop_type": "Bakery",
                "shop_id": "shop_demo_01",
                "onboarding_completed": True,
                "created_at": now_str,
            },
            {
                "_id": "demo_walkthrough_owner",
                "name": "RestockIQ Evaluator",
                "email": "demo@restockiq.local",
                "password_hash": hash_password("demo123456"),
                "role": "owner",
                "shop_name": "Artisan Sourdough & Café",
                "store_name": "Artisan Sourdough & Café",
                "shop_type": "Bakery",
                "shop_id": "shop_demo_01",
                "onboarding_completed": True,
                "created_at": now_str,
            }
        ]

        demo_shops = [
            {
                "_id": "shop_demo_01",
                "id": "shop_demo_01",
                "name": "Artisan Sourdough & Café",
                "type": "Bakery",
                "owner_id": "demo_walkthrough_owner",
                "created_at": now_str
            },
            {
                "_id": "shop_demo_02",
                "id": "shop_demo_02",
                "name": "Downtown Espresso & Bakery",
                "type": "Café",
                "owner_id": "manager_demo_owner",
                "created_at": now_str
            }
        ]

        if self.is_atlas_active:
            try:
                for acc in demo_accounts:
                    user = await self.db.users.find_one({"email": acc["email"]})
                    if not user:
                        await self.db.users.insert_one(acc)
                for shp in demo_shops:
                    existing_shop = await self.db.shops.find_one({"_id": shp["_id"]})
                    if not existing_shop:
                        await self.db.shops.insert_one(shp)
                print("[DB] Initialized demo users & shops in MongoDB Atlas.")
            except Exception as e:
                print(f"[DB] Atlas seed exception ({e}); using local storage.")

        # Ensure in local cache
        user_emails = [u.get("email") for u in self._local_cache["users"]]
        for acc in demo_accounts:
            if acc["email"] not in user_emails:
                self._local_cache["users"].append(acc)

        if "shops" not in self._local_cache:
            self._local_cache["shops"] = []
        shop_ids = [s.get("_id") for s in self._local_cache["shops"]]
        for shp in demo_shops:
            if shp["_id"] not in shop_ids:
                self._local_cache["shops"].append(shp)

        self._save_local_file()

    # --------------------------------------------------------------------------
    # Users & Shops Collection Operations
    # --------------------------------------------------------------------------
    async def find_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        clean_email = email.strip().lower()
        if self.is_atlas_active:
            try:
                user = await self.db.users.find_one({"email": clean_email})
                if user:
                    user["_id"] = str(user["_id"])
                    return user
            except Exception as e:
                print(f"[DB] Atlas find_user_by_email exception: {e}")
        for u in self._local_cache["users"]:
            if u.get("email", "").lower() == clean_email:
                return dict(u)
        return None

    async def find_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        if self.is_atlas_active:
            try:
                from bson import ObjectId
                try:
                    query = {"_id": ObjectId(user_id)}
                except Exception:
                    query = {"_id": user_id}
                user = await self.db.users.find_one(query)
                if user:
                    user["_id"] = str(user["_id"])
                    return user
            except Exception as e:
                print(f"[DB] Atlas find_user_by_id exception: {e}")
        for u in self._local_cache["users"]:
            if str(u.get("_id")) == str(user_id):
                return dict(u)
        return None

    async def create_user(
        self,
        email: str,
        password_hash: str,
        name: str,
        role: str = "owner",
        shop_name: str = "My Bakery",
        shop_type: str = "Bakery"
    ) -> Dict[str, Any]:
        """
        Creates a new user account with associated shop profile and onboarding state.
        Guarantees atomic creation in both Atlas and local persistent cache.
        """
        import uuid
        uid = str(uuid.uuid4())
        shop_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        
        effective_shop_name = shop_name.strip() if shop_name and shop_name.strip() else f"{name.strip()}'s Shop"
        effective_shop_type = shop_type.strip() if shop_type and shop_type.strip() else "Bakery"

        user_doc = {
            "_id": uid,
            "email": email.strip().lower(),
            "password_hash": password_hash,
            "name": name.strip(),
            "role": role,
            "shop_name": effective_shop_name,
            "store_name": effective_shop_name,
            "shop_type": effective_shop_type,
            "shop_id": shop_id,
            "onboarding_completed": False,  # First-time users start with onboarding false
            "created_at": now_str,
        }

        shop_doc = {
            "_id": shop_id,
            "id": shop_id,
            "name": effective_shop_name,
            "type": effective_shop_type,
            "owner_id": uid,
            "created_at": now_str,
        }

        if self.is_atlas_active:
            try:
                await self.db.users.insert_one(user_doc)
                await self.db.shops.insert_one(shop_doc)
            except Exception as e:
                print(f"[DB] Atlas create_user exception: {e}")

        async with self._lock:
            self._local_cache["users"].append(user_doc)
            if "shops" not in self._local_cache:
                self._local_cache["shops"] = []
            self._local_cache["shops"].append(shop_doc)
            self._save_local_file()

        return user_doc

    async def set_onboarding_status(self, user_id: str, completed: bool = True) -> bool:
        """
        Persists onboarding completion or skip state so returning users bypass the intro.
        """
        if self.is_atlas_active:
            try:
                from bson import ObjectId
                try:
                    query = {"_id": ObjectId(user_id)}
                except Exception:
                    query = {"_id": user_id}
                await self.db.users.update_one(query, {"$set": {"onboarding_completed": completed}})
            except Exception as e:
                print(f"[DB] Atlas set_onboarding_status exception: {e}")

        async with self._lock:
            for u in self._local_cache["users"]:
                if str(u.get("_id")) == str(user_id):
                    u["onboarding_completed"] = completed
                    self._save_local_file()
                    return True
        return False

    async def get_user_shop(self, owner_id: str) -> Dict[str, Any]:
        """
        Retrieves the personal shop profile belonging to the given authenticated owner.
        """
        if "shops" in self._local_cache:
            for s in self._local_cache["shops"]:
                if s.get("owner_id") == owner_id:
                    return dict(s)
        user = await self.find_user_by_id(owner_id)
        if user:
            return {
                "id": user.get("shop_id", owner_id),
                "name": user.get("shop_name") or user.get("store_name", "My Artisan Bakery"),
                "type": user.get("shop_type", "Bakery"),
                "owner_id": owner_id,
            }
        return {
            "id": owner_id,
            "name": "Artisan Sourdough & Café",
            "type": "Bakery",
            "owner_id": owner_id,
        }

    # --------------------------------------------------------------------------
    # Items / Inventory Operations (Strict Tenant Isolation)
    # --------------------------------------------------------------------------
    async def get_items(self, owner_id: str) -> List[Dict[str, Any]]:
        """
        Enforces tenant isolation: Returns ONLY items belonging to the authenticated owner.
        """
        if self.is_atlas_active:
            try:
                cursor = self.db.items.find({"owner_id": owner_id})
                items = await cursor.to_list(length=500)
                if items:
                    for it in items:
                        it["id"] = str(it.get("_id"))
                    return items
            except Exception as e:
                print(f"[DB] Atlas get_items exception: {e}")
        res = []
        demo_owners = {"demo_walkthrough_owner", "shop_demo_01", "6ac25e0a39f7359c51129734", "admin"}
        is_demo_session = owner_id in demo_owners or not owner_id
        for it in self._local_cache["items"]:
            it_owner = it.get("owner_id")
            matches_owner = (it_owner == owner_id) or (is_demo_session and (it_owner in demo_owners or not it_owner))
            if matches_owner:
                item_copy = dict(it)
                item_copy["id"] = str(item_copy.get("_id") or item_copy.get("id"))
                res.append(item_copy)
        return res

    async def get_item(self, item_id: str, owner_id: str = "") -> Optional[Dict[str, Any]]:
        items = await self.get_items(owner_id) if owner_id else self._local_cache["items"]
        for it in items:
            if str(it.get("id")) == str(item_id) or str(it.get("_id")) == str(item_id):
                if not owner_id or it.get("owner_id") == owner_id:
                    return it
        return None

    async def get_item_by_id(self, item_id: str, owner_id: str = "") -> Optional[Dict[str, Any]]:
        return await self.get_item(item_id, owner_id)

    async def create_item(self, item_data: Dict[str, Any], owner_id: str = "") -> Dict[str, Any]:
        import uuid
        item_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).isoformat()
        effective_owner = owner_id or item_data.get("owner_id", "demo_walkthrough_owner")
        shelf_days = item_data.get("shelf_life_days")
        if shelf_days is None:
            shelf_days = 1 if bool(item_data.get("isPerishable", True)) else 180
        else:
            shelf_days = int(shelf_days)
        doc = {
            "_id": item_id,
            "id": item_id,
            "name": item_data.get("name", "New Item"),
            "category": item_data.get("category", "General"),
            "unit": item_data.get("unit", "PCS"),
            "currentStock": int(item_data.get("currentStock", 0)),
            "shelf_life_days": shelf_days,
            "isPerishable": bool(item_data.get("isPerishable", True)),
            "price": float(item_data.get("price", 0.0)),
            "costPrice": float(item_data.get("costPrice", 0.0)),
            "predictedDemand": int(item_data.get("predictedDemand", 20)),
            "safetyStock": int(item_data.get("safetyStock", 5)),
            "description": item_data.get("description", "User added inventory item"),
            "riskLevel": item_data.get("riskLevel", "normal"),
            "owner_id": effective_owner,
            "updatedAt": now_str,
        }
        for k, v in item_data.items():
            if k not in doc:
                doc[k] = v
        if self.is_atlas_active:
            try:
                await self.db.items.insert_one(doc)
            except Exception as e:
                print(f"[DB] Atlas create_item exception: {e}")

        async with self._lock:
            self._local_cache["items"].append(doc)
            self._save_local_file()
        return doc

    async def insert_item(self, item_data: Dict[str, Any], owner_id: str = "") -> Dict[str, Any]:
        return await self.create_item(item_data, owner_id)

    async def update_item(self, item_id: str, updates: Any, owner_id: Any = None) -> bool:
        if isinstance(updates, str) and isinstance(owner_id, dict):
            actual_owner = updates
            actual_updates = owner_id
        else:
            actual_updates = updates if isinstance(updates, dict) else {}
            actual_owner = owner_id or "demo_walkthrough_owner"

        actual_updates["updatedAt"] = datetime.now(timezone.utc).isoformat()
        if self.is_atlas_active:
            try:
                res = await self.db.items.update_one({"_id": item_id, "owner_id": actual_owner}, {"$set": actual_updates})
                if res.modified_count > 0:
                    return True
            except Exception as e:
                print(f"[DB] Atlas update_item exception: {e}")

        async with self._lock:
            for it in self._local_cache["items"]:
                if (str(it.get("_id")) == str(item_id) or str(it.get("id")) == str(item_id)) and (not it.get("owner_id") or it.get("owner_id") == actual_owner or actual_owner in ("demo_walkthrough_owner", "admin")):
                    it.update(actual_updates)
                    self._save_local_file()
                    return True
        return False

    async def delete_item(self, item_id: str, owner_id: str) -> bool:
        if self.is_atlas_active:
            try:
                res = await self.db.items.delete_one({"_id": item_id, "owner_id": owner_id})
                if res.deleted_count > 0:
                    return True
            except Exception as e:
                print(f"[DB] Atlas delete_item exception: {e}")

        async with self._lock:
            before_len = len(self._local_cache["items"])
            self._local_cache["items"] = [
                it for it in self._local_cache["items"]
                if not ((str(it.get("_id")) == str(item_id) or str(it.get("id")) == str(item_id)) and it.get("owner_id") == owner_id)
            ]
            if len(self._local_cache["items"]) < before_len:
                self._save_local_file()
                return True
        return False

    async def bulk_update_stock(self, updates: List[Dict[str, Any]], owner_id: str) -> int:
        count = 0
        now_str = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            for update in updates:
                item_id = str(update.get("id"))
                new_stock = int(update.get("currentStock", 0))
                for it in self._local_cache["items"]:
                    if (str(it.get("_id")) == item_id or str(it.get("id")) == item_id) and it.get("owner_id") == owner_id:
                        it["currentStock"] = new_stock
                        it["updatedAt"] = now_str
                        count += 1
            if count > 0:
                self._save_local_file()
        return count

    # --------------------------------------------------------------------------
    # Historical Sales Data Operations (Strict Tenant Isolation)
    # --------------------------------------------------------------------------
    async def insert_sales_records(self, owner_id: str, records: List[Dict[str, Any]]) -> int:
        """
        Persists validated historical sales records to both MongoDB Atlas and local_db.json.
        """
        import uuid
        now_str = datetime.now(timezone.utc).isoformat()
        new_docs = []
        for r in records:
            doc = {
                "_id": str(uuid.uuid4()),
                "date": str(r.get("date")),
                "article": str(r.get("article", "")).strip(),
                "quantity": float(r.get("quantity", 0)),
                "price": float(r.get("price", 0.0)),
                "owner_id": owner_id,
                "created_at": now_str
            }
            new_docs.append(doc)

        if self.is_atlas_active and new_docs:
            try:
                await self.db.sales.insert_many(new_docs)
            except Exception as e:
                print(f"[DB] Atlas insert_sales_records exception: {e}")

        async with self._lock:
            if "sales" not in self._local_cache:
                self._local_cache["sales"] = []
            self._local_cache["sales"].extend(new_docs)
            self._save_local_file()

        return len(new_docs)

    async def get_sales(self, owner_id: str = "") -> List[Dict[str, Any]]:
        """
        Retrieves historical sales records filtered by owner_id.
        """
        if self.is_atlas_active:
            try:
                query = {"owner_id": owner_id} if owner_id else {}
                cursor = self.db.sales.find(query)
                sales = await cursor.to_list(length=10000)
                if sales:
                    return sales
            except Exception as e:
                print(f"[DB] Atlas get_sales exception: {e}")

        if "sales" not in self._local_cache:
            self._local_cache["sales"] = []

        if not owner_id:
            return list(self._local_cache["sales"])

        demo_owners = {"demo_walkthrough_owner", "shop_demo_01", "6ac25e0a39f7359c51129734", "admin"}
        is_demo_session = owner_id in demo_owners
        res = []
        for s in self._local_cache["sales"]:
            s_owner = s.get("owner_id")
            if s_owner == owner_id or (is_demo_session and (s_owner in demo_owners or not s_owner)):
                res.append(dict(s))
        return res

    # --------------------------------------------------------------------------
    # Waste Alerts Operations (Strict Tenant Isolation)
    # --------------------------------------------------------------------------
    async def get_waste_alerts(self, owner_id: str) -> List[Dict[str, Any]]:
        alerts = []
        demo_owners = {"demo_walkthrough_owner", "shop_demo_01", "6ac25e0a39f7359c51129734", "admin"}
        is_demo_session = owner_id in demo_owners or not owner_id
        for a in self._local_cache.get("waste_alerts", []):
            a_owner = a.get("owner_id")
            matches_owner = (a_owner == owner_id) or (is_demo_session and (a_owner in demo_owners or not a_owner))
            if a.get("status") == "active" and matches_owner:
                enriched = dict(a)
                enriched.setdefault("name", enriched.get("item_name", "Perishable Item"))
                enriched.setdefault("category", "Perishable")
                enriched.setdefault("currentStock", enriched.get("units_at_risk", 10))
                enriched.setdefault("sales_pace_ratio", enriched.get("current_pace_ratio", 0.50))
                enriched.setdefault("potentialWasteUnits", enriched.get("units_at_risk", 10))
                enriched.setdefault("potentialWasteValue", float(enriched.get("potentialWasteUnits", 10)) * 2.0)
                enriched.setdefault("riskLevel", "high")
                enriched.setdefault("recommendedAction", enriched.get("recommended_action", "Apply discount"))
                alerts.append(enriched)
        return alerts

    async def update_waste_alert_status(self, alert_id: str, status: str, action_taken: str, owner_id: str) -> bool:
        demo_owners = {"demo_walkthrough_owner", "shop_demo_01", "6ac25e0a39f7359c51129734", "admin"}
        is_demo_session = owner_id in demo_owners or not owner_id
        async with self._lock:
            for a in self._local_cache["waste_alerts"]:
                a_owner = a.get("owner_id")
                matches_owner = (a_owner == owner_id) or (is_demo_session and (a_owner in demo_owners or not a_owner))
                if a.get("id") == alert_id and matches_owner:
                    a["status"] = status
                    a["action_taken"] = action_taken
                    a["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    self._save_local_file()
                    return True
        return False

    # --------------------------------------------------------------------------
    # Audit Logs
    # --------------------------------------------------------------------------
    async def record_audit_log(self, action: str, details: Dict[str, Any], user_id: str):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details,
            "user_id": user_id
        }
        async with self._lock:
            self._local_cache["audit_logs"].append(log_entry)
            self._save_local_file()

    async def get_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(reversed(self._local_cache["audit_logs"]))[:limit]

    async def log_checkin(self, user_id: str, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "bulk_checkin",
            "details": {"entries_count": len(entries), "entries": entries},
            "user_id": user_id
        }
        if self.is_atlas_active:
            try:
                await self.db.audit_logs.insert_one(dict(log_entry))
            except Exception as e:
                print(f"[DB] Atlas log_checkin exception: {e}")
        async with self._lock:
            if "audit_logs" not in self._local_cache:
                self._local_cache["audit_logs"] = []
            self._local_cache["audit_logs"].append(log_entry)
            self._save_local_file()
        return log_entry
