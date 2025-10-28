#!/usr/bin/env python3
"""Clear all data from the database."""

from app.db.session import SessionLocal
from app.models.models import User, Invoice, InvoiceLine, WebhookEvent
from sqlalchemy import text

def main():
    db = SessionLocal()
    try:
        print('\n' + '=' * 80)
        print('CLEARING DATABASE')
        print('=' * 80 + '\n')
        
        # Get counts before deletion
        user_count = db.query(User).count()
        invoice_count = db.query(Invoice).count()
        invoice_line_count = db.query(InvoiceLine).count()
        
        print(f'Found {user_count} users')
        print(f'Found {invoice_count} invoices')
        print(f'Found {invoice_line_count} invoice lines')
        
        if user_count == 0 and invoice_count == 0:
            print('\n✓ Database is already empty!\n')
            return
        
        print('\nDeleting all data...')
        
        # Delete in correct order (respecting foreign keys)
        # 1. Delete invoice lines first
        db.query(InvoiceLine).delete()
        print('  ✓ Deleted all invoice lines')
        
        # 2. Delete invoices
        db.query(Invoice).delete()
        print('  ✓ Deleted all invoices')
        
        # 3. Delete webhook events if table exists
        try:
            db.query(WebhookEvent).delete()
            print('  ✓ Deleted all webhook events')
        except Exception:
            pass  # Table might not exist
        
        # 4. Delete users
        db.query(User).delete()
        print('  ✓ Deleted all users')
        
        # Reset auto-increment sequences (PostgreSQL)
        try:
            db.execute(text("ALTER SEQUENCE users_id_seq RESTART WITH 1"))
            db.execute(text("ALTER SEQUENCE invoices_id_seq RESTART WITH 1"))
            db.execute(text("ALTER SEQUENCE invoice_lines_id_seq RESTART WITH 1"))
            print('  ✓ Reset ID sequences')
        except Exception as e:
            print(f'  ⚠ Could not reset sequences: {e}')
        
        db.commit()
        
        print('\n' + '=' * 80)
        print('✓ DATABASE CLEARED SUCCESSFULLY')
        print('=' * 80 + '\n')
        
    except Exception as e:
        db.rollback()
        print(f'\n✗ Error clearing database: {e}\n')
        raise
    finally:
        db.close()

if __name__ == '__main__':
    main()
