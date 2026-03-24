'use client';

import { useState } from 'react';
import { useInboxPanels } from '@/contexts/InboxPanelsContext';
import { useToast } from '@/contexts/ToastContext';
import { PanelRight } from 'lucide-react';

/** Customer and store data (fetched from bot). Null or missing fields = new lead / not available. */
export interface ContextPanelCustomer {
  name?: string | null;
  phone?: string | null;
  email?: string | null;
  customerId?: string | null;
}

export interface ContextPanelStore {
  storeName?: string | null;
  storeCode?: string | null;
  storeType?: string | null;
}

interface ContextPanelProps {
  /** Customer info. Omit or pass null/empty for new lead. */
  customer?: ContextPanelCustomer | null;
  /** Store details. Omit or pass null/empty when no store. */
  store?: ContextPanelStore | null;
}

function placehold(value: string | null | undefined): string {
  return value?.trim() || '—';
}

export function ContextPanel(props: ContextPanelProps = {}) {
  const { customer: customerProp, store: storeProp } = props;
  const inboxPanels = useInboxPanels();
  const { toast } = useToast();
  const [internalNote, setInternalNote] = useState('');
  const [savingNote, setSavingNote] = useState(false);

  const customer = customerProp === undefined ? null : customerProp;
  const store = storeProp === undefined ? null : storeProp;
  const hasCustomer = customer != null && (customer.name || customer.phone || customer.email || customer.customerId);
  const hasStore = store != null && (store.storeName || store.storeCode || store.storeType);

  const handleSaveNote = () => {
    setSavingNote(true);
    setTimeout(() => {
      setSavingNote(false);
      toast('Note saved');
    }, 300);
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="space-y-6">
        <div>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-text-primary">Customer Info</h3>
            {inboxPanels && (
              <button
                type="button"
                onClick={inboxPanels.toggleContext}
                className="rounded p-1.5 text-text-secondary hover:bg-panel hover:text-primary transition-colors"
                title="Collapse context"
              >
                <PanelRight className="h-5 w-5" />
              </button>
            )}
          </div>
          {hasCustomer ? (
            <div className="space-y-3">
              <div>
                <p className="text-xs text-text-secondary mb-1">Name</p>
                <p className="text-sm text-text-primary">{placehold(customer?.name)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary mb-1">Phone</p>
                <p className="text-sm text-text-primary">{placehold(customer?.phone)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary mb-1">Email</p>
                <p className="text-sm text-text-primary">{placehold(customer?.email)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary mb-1">Customer ID</p>
                <p className="text-sm text-text-primary">{placehold(customer?.customerId)}</p>
              </div>
            </div>
          ) : (
            <p className="text-xs text-text-muted">No customer info yet. Data will appear when fetched from the conversation.</p>
          )}
        </div>

        <div className="border-t border-border pt-6">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Store Details</h3>
          {hasStore ? (
            <div className="space-y-3">
              <div>
                <p className="text-xs text-text-secondary mb-1">Store Name</p>
                <p className="text-sm text-text-primary">{placehold(store?.storeName)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary mb-1">Store Code</p>
                <p className="text-sm text-text-primary">{placehold(store?.storeCode)}</p>
              </div>
              <div>
                <p className="text-xs text-text-secondary mb-1">Store Type</p>
                <p className="text-sm text-text-primary">{placehold(store?.storeType)}</p>
              </div>
            </div>
          ) : (
            <p className="text-xs text-text-muted">No store linked. Show when available from the bot.</p>
          )}
        </div>

        <div className="border-t border-border pt-6">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Internal Notes</h3>
          <textarea
            placeholder="Add internal notes..."
            value={internalNote}
            onChange={(e) => setInternalNote(e.target.value)}
            className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-primary text-sm resize-none"
            rows={4}
          />
          <button
            type="button"
            onClick={handleSaveNote}
            disabled={savingNote}
            className="mt-2 px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-medium hover:bg-primary-dark disabled:opacity-50 transition-colors"
          >
            {savingNote ? 'Saving…' : 'Save Note'}
          </button>
        </div>
      </div>
    </div>
  );
}
