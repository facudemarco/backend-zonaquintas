from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from typing import List
import uuid
from datetime import datetime
from Database.getConnection import engine
from models.wallet import TransactionCreate, TransactionStatusUpdate
from utils.security import get_current_user

router = APIRouter()

def ensure_wallet_table_exists():
    """Crea la tabla transactions matemáticamente para soportar el módulo de Mi Wallet"""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                id VARCHAR(36) PRIMARY KEY,
                owner_id VARCHAR(36) NOT NULL,
                quinta_id VARCHAR(36),
                amount DECIMAL(15,2) NOT NULL,
                currency ENUM('ARS', 'USD') NOT NULL,
                status ENUM('RETENIDO', 'DISPONIBLE', 'ENTREGADO', 'CANCELADO') NOT NULL DEFAULT 'RETENIDO',
                transfer_date_estimate DATE,
                description VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """))

# Execute the table creation when the router is loaded
ensure_wallet_table_exists()

@router.get("/dashboard", tags=["Wallet"])
async def get_wallet_dashboard(current_user: str = Depends(get_current_user)):
    """
    Entrega el listado de balances proyectado en base al motor transaccional
    y las últimas transacciones para renderizar en el panel de control del dueño.
    """
    try:
        with engine.begin() as conn:
            # En un sistema real extraeriamos todas las trasancciones filtradas por owner_id
            # current_user será el user_id.
            
            # Fetch all transactions with quinta titles mapped for this user
            result = conn.execute(
                text("""
                    SELECT t.*, q.title as quinta_title 
                    FROM transactions t
                    LEFT JOIN quintas q ON t.quinta_id = q.id
                    WHERE t.owner_id = :owner_id 
                    ORDER BY t.created_at DESC
                """),
                {"owner_id": current_user}
            )
            transactions = result.mappings().all()

            # Initialize balances
            balances = {
                "retenido": {"ARS": 0.0, "USD": 0.0},
                "disponible": {"ARS": 0.0, "USD": 0.0},
                "entregado": {"ARS": 0.0, "USD": 0.0}
            }

            next_transfer_date = None
            recent_tx_list = []

            for tx in transactions:
                # Accumulate balances mathematically across transactions
                status = tx["status"].lower()
                currency = tx["currency"]
                
                # We skip canceled transactions for the balances
                if status in balances:
                    balances[status][currency] += float(tx["amount"])

                # Determine nearest future transfer date
                if tx["status"] in ("RETENIDO", "DISPONIBLE"):
                    tx_date = tx.get("transfer_date_estimate")
                    if tx_date:
                        if next_transfer_date is None or tx_date < next_transfer_date:
                            next_transfer_date = tx_date

                # Append for the movement history list
                recent_tx_list.append({
                    "id": tx["id"],
                    "date": tx["created_at"].strftime("%d/%m/%Y"),
                    "quinta_name": tx["quinta_title"] if tx["quinta_title"] else "N/A",
                    "amount": float(tx["amount"]),
                    "currency": tx["currency"],
                    "status": tx["status"],
                    "description": tx["description"]
                })

            return {
                "balances": balances,
                "next_transfer": next_transfer_date.strftime("%d/%m/%Y") if next_transfer_date else None,
                "recent_transactions": recent_tx_list
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/transactions", tags=["Wallet"])
async def create_transaction(
    data: TransactionCreate, 
    current_user: str = Depends(get_current_user) # Idealmente solo admin puede crear esto (Ej. una validación)
):
    """Crea una nueva retención vinculada a una reserva"""
    try:
        tx_id = str(uuid.uuid4())
        
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO transactions 
                    (id, owner_id, quinta_id, amount, currency, status, transfer_date_estimate, description) 
                    VALUES (:id, :owner_id, :quinta_id, :amount, :currency, :status, :transfer_date_estimate, :description)
                """),
                {
                    "id": tx_id,
                    "owner_id": data.owner_id,
                    "quinta_id": data.quinta_id,
                    "amount": data.amount,
                    "currency": data.currency.value,
                    "status": data.status.value,
                    "transfer_date_estimate": data.transfer_date_estimate,
                    "description": data.description
                }
            )
        return {"message": "Transacción creada y registrada en la wallet", "id": tx_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/transactions/{transaction_id}/status", tags=["Wallet"])
async def update_transaction_status(
    transaction_id: str, 
    data: TransactionStatusUpdate,
    current_user: str = Depends(get_current_user) # Only admins should do this
):
    """Actualiza manual y explícitamente el estado de un bloque de dinero"""
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("UPDATE transactions SET status = :status WHERE id = :id"),
                {"status": data.status.value, "id": transaction_id}
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Transacción no encontrada")

        return {"message": f"Estado de transacción actualizado a {data.status.value}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/payout/{owner_id}", tags=["Wallet"])
async def trigger_manual_payout(
    owner_id: str,
    current_user: str = Depends(get_current_user) 
):
    """
    Libera todos los fondos 'DISPONIBLE' de un Propietario a 'ENTREGADO'.
    Este botón se aprieta cuando Admin deposita en la cuenta de dicho dueño.
    """
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE transactions 
                    SET status = 'ENTREGADO' 
                    WHERE owner_id = :owner_id AND status = 'DISPONIBLE'
                """),
                {"owner_id": owner_id}
            )
            if result.rowcount == 0:
                return {"message": "No había fondos en estado DISPONIBLE para entregar. Nada cambió."}
                
        return {"message": f"Pago marcado como ENTREGADO masivamente. {result.rowcount} transacciones afectadas."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
