from typing import Literal
from pydantic import BaseModel, Field, model_validator, ValidationInfo

class LineItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float

class InvoiceData(BaseModel):
    action_type: Literal["EXTRACT_INVOICE"] = "EXTRACT_INVOICE"
    vendor_name: str = Field(..., description="The name of the company that issued the invoice.")
    invoice_number: str
    date: str = Field(..., description="The date the invoice was issued (YYYY-MM-DD)")
    line_items: list[LineItem] = Field(..., min_length=1)
    subtotal: float = Field(..., description="The subtotal before tax.")
    tax_amount: float = Field(..., description="The tax amount.")
    total_amount: float = Field(..., description="The final total amount.")
    reasoning: str = Field(..., description="Explain any discrepancies or assumptions made.")

    @model_validator(mode='after')
    def check_math(self, info: ValidationInfo):
        # Business Rule 1: Line item totals must equal quant * unit_price
        for i, item in enumerate(self.line_items):
            expected = round(item.quantity * item.unit_price, 2)
            if round(item.total, 2) != expected:
                raise ValueError(f"Math Error on line item {i+1} ('{item.description}'): quantity ({item.quantity}) * unit_price ({item.unit_price}) equals {expected}, but you extracted {item.total}.")
                
        # Business Rule 2: Subtotal must equal sum of line item totals
        calc_subtotal = sum(item.total for item in self.line_items)
        if round(self.subtotal, 2) != round(calc_subtotal, 2):
            raise ValueError(f"Math Error: The sum of the line item totals is {calc_subtotal}, but the extracted subtotal is {self.subtotal}.")
            
        # Business Rule 3: Total amount must equal subtotal + tax
        calc_total = self.subtotal + self.tax_amount
        if round(self.total_amount, 2) != round(calc_total, 2):
            raise ValueError(f"Math Error: Subtotal ({self.subtotal}) + Tax ({self.tax_amount}) equals {calc_total}, but the extracted total_amount is {self.total_amount}.")
            
        return self

class MedicalRecordData(BaseModel):
    action_type: Literal["EXTRACT_MEDICAL_RECORD"] = "EXTRACT_MEDICAL_RECORD"
    patient_name: str
    age: int
    height_cm: float = Field(..., description="Height in centimeters")
    weight_kg: float = Field(..., description="Weight in kilograms")
    bmi: float = Field(..., description="Body Mass Index")
    blood_pressure: str = Field(..., description="e.g. 120/80")
    reasoning: str = Field(..., description="Explain any discrepancies or assumptions made.")

    @model_validator(mode='after')
    def check_bmi(self, info: ValidationInfo):
        if self.height_cm <= 0:
            raise ValueError("Math Error: height_cm cannot be zero or negative.")
            
        # BMI = weight_kg / (height_m)^2
        height_m = self.height_cm / 100
        expected_bmi = round(self.weight_kg / (height_m ** 2), 1)
        
        # Give a small 0.1 margin of error for rounding
        if abs(round(self.bmi, 1) - expected_bmi) > 0.1:
            raise ValueError(f"Math Error: weight_kg ({self.weight_kg}) / (height_m ({height_m}) ^ 2) equals {expected_bmi}, but the extracted BMI is {self.bmi}. You must calculate and output the mathematically correct BMI, even if the PDF is wrong.")
        return self
