from sqlalchemy import Column, Integer, String, TIMESTAMP, text, ForeignKey
from db.init import Base

class SubscriptionPlanSchedule(Base):
    """
    Stores the active month range for each subscription plan.
    Subscriptions are automatically paused during inactive months.
    """
    __tablename__ = "subscription_plan_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)
    plan_name = Column(String(100), nullable=False)  # For easy reference (Turf, Mosquito, Ground Control)
    start_month = Column(Integer, nullable=False)     # 1-12 (January = 1)
    end_month = Column(Integer, nullable=False)       # 1-12 (November = 11)
    created_at = Column(TIMESTAMP, server_default=text("NOW()"))
    
    def is_month_active(self, month: int) -> bool:
        """
        Check if the given month (1-12) falls within the active range.
        Handles wrap-around for schedules that span year boundaries (though not currently needed).
        """
        if self.start_month <= self.end_month:
            # Normal range: Jan-Nov = 1-11
            return self.start_month <= month <= self.end_month
        else:
            # Wrap-around range: e.g., Nov-Feb = 11-2
            return month >= self.start_month or month <= self.end_month
