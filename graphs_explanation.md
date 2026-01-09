# Admin Analytics Explanation

This document explains the data sources and logic behind the charts on your Admin Dashboard.

## 1. Customer Growth (Area Chart)
- **Data Source**: Local Database (`customers` table).
- **Explanation**: Shows the **Total Registered Users** over the last 30 days. 
- **Calculation**: It takes the total user count before 30 days and adds daily new signups to show a cumulative growth curve.

## 2. Active Subscription Plans (Bar Chart)
- **Data Source**: **Live Square API**.
- **Explanation**: Shows the distribution of users across different plans (e.g., Mosquito Control vs. Lawn Care).
- **Logic**: Every time you load the page, we query Square for all `ACTIVE` subscriptions and group them by their Plan ID.

## 3. Revenue Breakdown by Plan (Horizontal Bar Chart)
- **Data Source**: **Live Square API**.
- **Explanation**: Shows the **Dollar Value ($)** each plan contributes to your Monthly Recurring Revenue (MRR).
- **Calculation**: Matches each active subscription in Square to its current price in your Square Catalog. This helps identify which services are your primary revenue drivers.

---

> [!NOTE]
> Values like **Active Subscribers** and **MRR** at the top are also pulled live from Square to ensure you always see the most accurate billing data.
