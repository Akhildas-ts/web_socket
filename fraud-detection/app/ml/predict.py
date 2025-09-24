import numpy as np
from datetime import datetime
from typing import List, Tuple, Optional

from schemas.transaction import TransactionCreate, RiskAssessment
from db.models import user_profiles, blacklisted_ips

def extract_features(transaction: TransactionCreate) -> np.array:
    """Extract features from transaction for ML model"""
    
    # Time-based features
    current_time = datetime.now()
    hour = current_time.hour
    is_weekend = current_time.weekday() >= 5
    is_late_night = hour < 6 or hour > 22
    
    # User profile features
    user_profile = user_profiles.get(transaction.user_id)
    
    # Base features
    features = [
        transaction.amount,                    # 0: Transaction amount
        hour,                                 # 1: Hour of day
        int(is_weekend),                      # 2: Is weekend
        int(is_late_night),                   # 3: Is late night
        len(transaction.merchant_category),   # 4: Merchant category length (proxy)
        len(transaction.location),            # 5: Location length (proxy)
        0,  # 6: Amount deviation (will be calculated if user profile exists)
        0,  # 7: Location risk
        0,  # 8: Merchant risk  
        0   # 9: Account age (normalized)
    ]
    
    # User profile adjustments
    if user_profile:
        # Amount deviation from user's average
        if user_profile.avg_transaction_amount > 0:
            amount_deviation = abs(transaction.amount - user_profile.avg_transaction_amount) / user_profile.avg_transaction_amount
            features[6] = min(amount_deviation, 5.0)  # Cap at 5x deviation
        
        # Location risk (1 if not in preferred locations, 0 if preferred)
        features[7] = 0 if transaction.location in user_profile.preferred_locations else 1
        
        # Merchant risk (1 if not in preferred merchants, 0 if preferred)
        features[8] = 0 if transaction.merchant_category in user_profile.preferred_merchants else 1
        
        # Account age (normalized to years, capped at 2)
        features[9] = min(user_profile.account_age_days / 365.0, 2.0)
    
    return np.array(features).reshape(1, -1)

def apply_business_rules(transaction: TransactionCreate, redis_client) -> Tuple[float, List[str]]:
    """Apply business rules to calculate additional risk score"""
    rule_score = 0.0
    reasons = []
    
    # High amount transactions
    if transaction.amount > 5000:
        rule_score += 25
        reasons.append("Very high transaction amount")
    elif transaction.amount > 1000:
        rule_score += 15
        reasons.append("High transaction amount")
    
    # Suspicious IP address
    if transaction.ip_address and transaction.ip_address in blacklisted_ips:
        rule_score += 30
        reasons.append("Blacklisted IP address")
    
    # User profile-based rules
    user_profile = user_profiles.get(transaction.user_id)
    if user_profile:
        # Amount significantly higher than user average
        if transaction.amount > user_profile.avg_transaction_amount * 5:
            rule_score += 20
            reasons.append("Amount 5x higher than user average")
        elif transaction.amount > user_profile.avg_transaction_amount * 3:
            rule_score += 10
            reasons.append("Amount 3x higher than user average")
        
        # Unusual location
        if transaction.location not in user_profile.preferred_locations:
            rule_score += 12
            reasons.append("Transaction from unusual location")
        
        # Unusual merchant category
        if transaction.merchant_category not in user_profile.preferred_merchants:
            rule_score += 8
            reasons.append("Unusual merchant category for user")
    
    # Velocity checks using Redis
    if redis_client:
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            user_tx_key = f"user_transactions:{transaction.user_id}:{today}"
            transaction_count = redis_client.get(user_tx_key)
            
            if transaction_count:
                count = int(transaction_count)
                if count > 20:
                    rule_score += 25
                    reasons.append("Extremely high transaction velocity (20+ today)")
                elif count > 10:
                    rule_score += 15
                    reasons.append("High transaction velocity (10+ today)")
                elif count > 5:
                    rule_score += 8
                    reasons.append("Elevated transaction velocity")
        except Exception as e:
            # Redis error, continue without velocity check
            pass
    
    # Time-based rules
    hour = datetime.now().hour
    if hour < 6 or hour > 22:
        rule_score += 10
        reasons.append("Late night transaction")
    
    # Payment method risk
    if transaction.payment_method == "digital_wallet":
        rule_score += 5
        reasons.append("Digital wallet payment (slightly higher risk)")
    
    # Device fingerprint check (simplified)
    if not transaction.device_fingerprint:
        rule_score += 8
        reasons.append("No device fingerprint provided")
    
    return rule_score, reasons

def get_risk_level(risk_score: float) -> str:
    """Convert risk score to categorical risk level"""
    if risk_score < 25:
        return "LOW"
    elif risk_score < 50:
        return "MEDIUM"  
    elif risk_score < 75:
        return "HIGH"
    else:
        return "CRITICAL"

def get_recommended_action(risk_score: float) -> str:
    """Get recommended action based on risk score"""
    if risk_score < 30:
        return "APPROVE"
    elif risk_score < 55:
        return "REVIEW"
    elif risk_score < 80:
        return "REQUEST_VERIFICATION"
    else:
        return "DECLINE"

def analyze_transaction_risk(
    transaction: TransactionCreate,
    model,
    scaler, 
    redis_client
) -> RiskAssessment:
    """Main function to analyze transaction risk using ML + business rules"""
    
    # Extract features for ML model
    features = extract_features(transaction)
    
    # Get ML-based anomaly score
    ml_risk_score = 0.0
    if model and scaler:
        try:
            # Scale features
            scaled_features = scaler.transform(features)
            
            # Get anomaly score from Isolation Forest
            anomaly_score = model.decision_function(scaled_features)[0]
            
            # Convert anomaly score to 0-100 risk score
            # Isolation Forest returns negative scores for anomalies
            ml_risk_score = max(0, min(100, (0.5 - anomaly_score) * 50))
            
        except Exception as e:
            # Model error, continue with rules-based approach
            ml_risk_score = 20.0  # Default moderate score
    
    # Apply business rules
    rule_score, rule_reasons = apply_business_rules(transaction, redis_client)
    
    # Combine ML score with business rules
    final_risk_score = min(100.0, ml_risk_score + rule_score)
    
    # Add ML reason if score is elevated
    all_reasons = rule_reasons.copy()
    if ml_risk_score > 40 and not rule_reasons:
        all_reasons.append("ML model detected anomalous transaction pattern")
    
    # Calculate confidence score
    confidence = min(1.0, (final_risk_score / 100.0) + 0.3)
    if rule_reasons:  # Higher confidence when business rules trigger
        confidence = min(1.0, confidence + 0.2)
    
    return RiskAssessment(
        transaction_id="",  # Will be set by calling function
        risk_score=round(final_risk_score, 2),
        risk_level=get_risk_level(final_risk_score),
        confidence=round(confidence, 2),
        reasons=all_reasons,
        recommended_action=get_recommended_action(final_risk_score)
    )