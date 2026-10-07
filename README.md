# backend-zonaquintas

## Esquema administrativo

Las tablas del CRM se crean ejecutando `Database/admin_crm_schema.sql` sobre
la misma base MySQL que usa el backend. El script es aditivo y usa
`CREATE TABLE IF NOT EXISTS`; no elimina datos ni modifica las tablas del
marketplace. Debe ejecutarse antes de usar verificaciones, auditoría o liquidaciones.

El dashboard puede consultarse antes de instalar este esquema: si todavía no
existe `quinta_verifications`, cuenta todas las quintas como pendientes. Es el
mismo criterio que aplica a una quinta sin registro de verificación cuando la
tabla ya existe. Los demás errores de base de datos siguen propagándose.

## Validación

```bash
python -m pytest tests -q
```
