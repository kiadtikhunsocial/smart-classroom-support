export type SalesRecordKind = 'deal' | 'payment_request';
export type DealStatus = 'interested' | 'quoted' | 'won' | 'lost';
export type PaymentRequestStatus = 'requested' | 'reviewing' | 'resolved' | 'cancelled';

export interface SalesLead {
  id: number;
  user_id?: string | null;
  name: string;
  phone: string;
  interest: string;
  products: string;
  source: string;
  note: string;
  status: string;
  created_at: string;
}

export interface SalesRecord {
  id: number;
  lead_id: number;
  lead_name: string;
  kind: SalesRecordKind;
  product: string;
  quantity: number;
  amount_thb: string | null;
  status: DealStatus | PaymentRequestStatus;
  note: string;
  created_by: number | null;
  created_at: string;
  updated_at: string | null;
}

export interface SalesSummary {
  lead_count: number;
  demo_lead_count: number;
  open_deals: number;
  won_deals: number;
  won_amount_thb: string;
  payment_requests: number;
  deal_status_counts?: Record<string, number>;
  lead_by_source?: Record<string, number>;
  new_leads_7d?: number;
}
