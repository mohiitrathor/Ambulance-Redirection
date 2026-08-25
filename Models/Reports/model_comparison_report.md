# Model Comparison & Final Model Selection

## 1. Objective

The objective of the machine learning stage is to classify emergency incidents into five severity levels:

- Non-Urgent
- Low
- Moderate
- Emergency
- Critical

The models were evaluated using the same patient incident dataset, feature set, train/test split, and evaluation methodology.

The primary evaluation metric is **Balanced Accuracy**, rather than ordinary accuracy, because the severity classes are imbalanced.

## 2. Dataset and Evaluation Setup

- Total samples: **100,000**
- Training samples: **80,000**
- Testing samples: **20,000**
- Input features: **24**
- Numeric features: **18**
- Categorical features: **6**
- Target: **Severity**

Excluded columns:

- `Incident_ID` — identifier only
- `Patient_Lat`, `Patient_Lon` — location information, not used for initial clinical severity prediction
- `Clinical_Score` — synthetic rule-based reference score derived from clinical variables
- `Ambulance_Priority` — directly derived from `Severity`
- `Severity` — target variable

The train/test split used stratification to preserve the severity distribution.

## 3. Models Evaluated

1. Logistic Regression
2. Random Forest
3. XGBoost
4. HistGradientBoosting

Logistic Regression and XGBoost were subsequently tuned using 5-fold stratified cross-validation.

## 4. Initial Model Comparison

| Model | Accuracy | Balanced Accuracy |
|---|---:|---:|
| **Logistic Regression** | **68.95%** | **67.07%** |
| XGBoost | 68.21% | 66.21% |
| HistGradientBoosting | 67.85% | 66.14% |
| Random Forest | 66.33% | 63.12% |

Logistic Regression was the strongest initial model on both accuracy and balanced accuracy.

## 5. Why Balanced Accuracy Was Prioritized

The target classes are imbalanced:

| Severity | Percentage |
|---|---:|
| Emergency | 33.22% |
| Moderate | 29.17% |
| Critical | 18.03% |
| Low | 14.11% |
| Non-Urgent | 5.47% |

Ordinary accuracy can hide poor performance on less frequent classes. Balanced accuracy gives each class equal importance through its recall.

For an emergency-severity system, this makes it a more informative primary metric than raw accuracy alone.

## 6. Initial Logistic Regression

Initial results:

- Accuracy: **68.95%**
- Balanced Accuracy: **67.07%**
- Critical recall: **68.64%**
- Emergency recall: **71.58%**
- Moderate recall: **71.20%**
- Low recall: **60.77%**
- Non-Urgent recall: **63.16%**

Most errors occurred between neighboring severity levels:

- Low ↔ Moderate
- Moderate ↔ Emergency
- Emergency ↔ Critical

## 7. Random Forest

Random Forest achieved:

- Accuracy: **66.33%**
- Balanced Accuracy: **63.12%**

It performed worse than Logistic Regression on both primary metrics and was not selected for further tuning.

## 8. XGBoost

XGBoost achieved:

- Accuracy: **68.21%**
- Balanced Accuracy: **66.21%**

It performed better than Random Forest but remained below Logistic Regression.

Its balanced accuracy was approximately **0.86 percentage points lower** than the initial Logistic Regression model, so it was tested further through hyperparameter tuning.

## 9. HistGradientBoosting

HistGradientBoosting achieved:

- Accuracy: **67.85%**
- Balanced Accuracy: **66.14%**

It performed better than Random Forest but remained below Logistic Regression and was not selected for further tuning.

# 10. Logistic Regression Hyperparameter Tuning

Logistic Regression was tuned using:

- 5-fold Stratified Cross-Validation
- Balanced Accuracy as the scoring metric
- An untouched 20% test set

The best configuration was:

```text
C = 1
class_weight = balanced
solver = lbfgs
```

Best cross-validation balanced accuracy:

**69.28%**

Final test results:

- Accuracy: **67.11%**
- Balanced Accuracy: **70.16%**

Compared with the original Logistic Regression:

```text
Balanced Accuracy:
67.07% → 70.16%

Improvement:
+3.09 percentage points
```

Although raw accuracy decreased, balanced accuracy improved substantially, indicating better performance across the severity classes.

## 11. Critical-Class Performance

Critical recall improved from:

**68.64% → 79.95%**

This is an improvement of **11.31 percentage points**.

The tradeoff was a decrease in Emergency recall:

**71.58% → 62.00%**

This behavior is consistent with using `class_weight="balanced"`, which increases the importance of less frequent classes.

## 12. XGBoost Hyperparameter Tuning

XGBoost was also tuned using 5-fold stratified cross-validation.

Best configuration:

```text
n_estimators = 200
max_depth = 6
learning_rate = 0.1
subsample = 0.8
colsample_bytree = 0.8
```

Best cross-validation balanced accuracy:

**65.49%**

Final test results:

- Accuracy: **68.21%**
- Balanced Accuracy: **66.21%**

Tuning did not improve the original XGBoost result.

The best configuration also showed a notable training/CV gap:

```text
Training balanced accuracy: ~75.33%
Cross-validation balanced accuracy: ~65.49%
```

This indicates weaker generalization compared with Logistic Regression on the current dataset.

## 13. Final Comparison

| Model | Test Accuracy | Test Balanced Accuracy | Decision |
|---|---:|---:|---|
| Logistic Regression | 68.95% | 67.07% | Initial winner |
| Random Forest | 66.33% | 63.12% | Rejected |
| XGBoost | 68.21% | 66.21% | Tuned, not selected |
| HistGradientBoosting | 67.85% | 66.14% | Rejected |
| **Tuned Logistic Regression** | **67.11%** | **70.16%** | **Selected** |
| Tuned XGBoost | 68.21% | 66.21% | Rejected |

## 14. Why Logistic Regression Was Selected

### 1. Highest balanced accuracy

The tuned Logistic Regression achieved **70.16% balanced accuracy**, the highest among the evaluated models.

### 2. Better minority-class performance

`class_weight="balanced"` improved performance on less frequent severity classes.

Critical recall increased from **68.64% to 79.95%**.

### 3. Better generalization

Logistic Regression showed a smaller gap between training and cross-validation performance than XGBoost during tuning.

### 4. Interpretability

Logistic Regression is easier to interpret than the tree-based ensemble models evaluated. This is valuable for understanding which clinical features influence severity predictions.

### 5. Simplicity and efficiency

The selected model is comparatively lightweight and straightforward to deploy. The additional complexity of the tree-based models did not produce better balanced accuracy on this dataset.

## 15. Final Model

The selected model is:

```text
Tuned Logistic Regression

C = 1
class_weight = balanced
solver = lbfgs

Test Accuracy:          67.11%
Test Balanced Accuracy: 70.16%
Critical Recall:        79.95%
```

This model will be used as the current clinical severity classification model for the next stage of the project.

## 16. Important Limitation

The dataset is synthetic.

The patient severity labels were generated as part of the synthetic data-generation process, and several clinical features were subsequently generated using the latent severity.

Therefore, these performance results should **not** be interpreted as real-world clinical accuracy.

The results demonstrate the machine learning pipeline and model-selection process on the synthetic dataset.

Real-world medical use would require appropriately sourced clinical data, clinical validation, safety evaluation, calibration, and expert oversight.

## 17. Next Steps

1. Analyze Logistic Regression feature coefficients.
2. Determine which clinical variables contribute most to each severity class.
3. Perform detailed error analysis.
4. Examine Critical and Emergency misclassifications.
5. Build the final preprocessing + model inference pipeline.
6. Integrate severity prediction into the ambulance dispatch system.

## Conclusion

Four classification algorithms were evaluated using the same dataset and evaluation methodology.

The initial Logistic Regression model achieved the strongest overall baseline performance. Hyperparameter tuning further improved its balanced accuracy from **67.07% to 70.16%**.

The tuned model also improved Critical recall from **68.64% to 79.95%**.

Although XGBoost achieved competitive overall accuracy, its balanced accuracy remained lower and its tuning results showed weaker generalization.

Therefore, **Tuned Logistic Regression was selected as the final severity classification model for the current synthetic dataset**.
