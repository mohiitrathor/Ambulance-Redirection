# Synthetic EMS Dataset

## Overview

This project uses a synthetic emergency medical services (EMS) environment designed specifically for developing and testing an **AI-powered ambulance priority, dispatch, ETA prediction, hospital selection, and dynamic routing system**.

The dataset is completely synthetic and generated using Python, NumPy, and Pandas. It does **not** represent real patients, real ambulance locations, or real hospitals.

The synthetic environment consists of four interconnected datasets:

1. `patient_incidents.csv`
2. `ambulances.csv`
3. `hospitals.csv`
4. `dispatch_scenarios.csv`

The datasets are generated with relationships between medical conditions, physiological measurements, emergency severity, ambulance capabilities, traffic conditions, and travel time.

---

# 1. Patient Incidents Dataset

**File:** `patient_incidents.csv`

**Records:** 100,000 patients

This dataset represents simulated emergency incidents and their associated patient information.

Each patient is generated from an underlying medical condition and latent severity. Clinical observations such as vital signs and symptoms are then generated based on those factors.

This prevents the dataset from being simply independent random values.

## Main columns

| Column | Description |
|---|---|
| `Incident_ID` | Unique identifier for the emergency incident |
| `Age` | Patient age |
| `Sex` | Patient sex |
| `Condition` | Primary simulated medical condition |
| `Heart_Rate` | Heart rate in beats per minute |
| `SpO2` | Blood oxygen saturation percentage |
| `Systolic_BP` | Systolic blood pressure |
| `Diastolic_BP` | Diastolic blood pressure |
| `Respiratory_Rate` | Respiratory rate |
| `Temperature` | Body temperature in °C |
| `GCS` | Glasgow Coma Scale score |
| `Pain_Score` | Pain score from 0–10 |
| `Blood_Glucose` | Blood glucose level |
| `Oxygen_Requirement` | Simulated oxygen support requirement |
| `Respiratory_Distress` | Whether respiratory distress is present |
| `Chest_Pain` | Whether chest pain is present |
| `Consciousness` | Simulated consciousness state |
| `Bleeding` | Whether bleeding is present |
| `Seizure` | Whether seizure activity is present |
| `Injury_Type` | Type of injury, if applicable |
| `Diabetes` | Simulated diabetes history |
| `Hypertension` | Simulated hypertension history |
| `Heart_Disease` | Simulated heart disease history |
| `Respiratory_Disease` | Simulated respiratory disease history |
| `Arrival_Mode` | Walk-in, ambulance, or referral |
| `Patient_Lat` | Simulated patient latitude |
| `Patient_Lon` | Simulated patient longitude |
| `Clinical_Score` | Rule-based reference severity score |
| `Severity` | Target emergency severity class |
| `Ambulance_Priority` | Dispatch priority derived from severity |

## Severity classes

The dataset contains five severity levels:

| Severity | Meaning | Priority |
|---|---|---|
| `Non-Urgent` | Low-risk situation | P5 |
| `Low` | Minor urgency | P4 |
| `Moderate` | Requires medical attention | P3 |
| `Emergency` | Serious emergency | P2 |
| `Critical` | Life-threatening emergency | P1 |

The `Severity` column is the primary target for the severity prediction model.

### Important

`Clinical_Score` should **not** be used as an input feature when training the severity model.

It is a reference score generated from clinical indicators and is retained for analysis and comparison.

Using it as a model feature would introduce target leakage because it contains information directly related to the severity-generation process.

---

# 2. Ambulance Dataset

**File:** `ambulances.csv`

**Records:** 1,000 ambulances

This dataset represents the simulated ambulance fleet available to the emergency response system.

Each ambulance has a location, type, and current availability state.

## Columns

| Column | Description |
|---|---|
| `Ambulance_ID` | Unique ambulance identifier |
| `Ambulance_Type` | Type/capability of ambulance |
| `Latitude` | Current simulated latitude |
| `Longitude` | Current simulated longitude |
| `Availability` | Current operational status |

## Ambulance types

### Basic Life Support

Designed for lower-acuity cases where advanced critical-care capabilities are not required.

### Advanced Life Support

Represents ambulances equipped for higher-acuity emergencies.

### Critical Care

Represents the highest-capability ambulance category for critical patients.

## Availability states

```text
Available
Busy
Maintenance
```

Only available ambulances are considered when generating dispatch candidates.

---

# 3. Hospital Dataset

**File:** `hospitals.csv`

**Records:** 300 hospitals

This dataset represents the simulated hospitals available to receive emergency patients.

## Columns

| Column | Description |
|---|---|
| `Hospital_ID` | Unique hospital identifier |
| `Hospital_Type` | Type/specialization of hospital |
| `Latitude` | Simulated hospital latitude |
| `Longitude` | Simulated hospital longitude |
| `Hospital_Capacity` | Total simulated capacity |
| `Current_Load` | Current simulated hospital load |
| `ICU_Capacity` | Total simulated ICU capacity |
| `Current_ICU_Load` | Current simulated ICU occupancy |

## Hospital types

```text
General
Trauma Center
Cardiac Center
Specialty Hospital
```

The hospital dataset is intended to support future hospital-selection logic.

For example, a critical trauma patient could be prioritized toward an appropriate trauma-capable facility rather than simply choosing the geographically closest hospital.

---

# 4. Dispatch Scenarios Dataset

**File:** `dispatch_scenarios.csv`

**Records:** approximately 500,000 scenarios

This dataset connects emergency incidents with possible ambulance assignments.

Each patient incident is paired with five candidate available ambulances.

Therefore:

```text
100,000 incidents × 5 candidates
≈ 500,000 dispatch scenarios
```

This dataset is intended for developing the ambulance dispatch and ETA components of the system.

## Columns

| Column | Description |
|---|---|
| `Incident_ID` | Emergency incident identifier |
| `Ambulance_ID` | Candidate ambulance identifier |
| `Patient_Severity` | Severity of the associated patient |
| `Ambulance_Type` | Type of candidate ambulance |
| `Distance_KM` | Approximate distance between ambulance and patient |
| `Traffic_Level` | Simulated traffic condition |
| `Road_Condition` | Simulated road quality |
| `Base_Speed_KMH` | Estimated base travel speed |
| `Predicted_ETA_Minutes` | Simulated travel time |
| `Capability_Match` | Whether the ambulance is suitable for the patient |
| `Dispatch_Score` | Score used to rank candidate ambulances |
| `Selected` | Whether this ambulance was selected as the best candidate |

---

# Data Generation Logic

The datasets are not generated as completely independent random values.

The patient generation process follows:

```text
Medical Condition
       ↓
Underlying Severity
       ↓
Clinical State
       ↓
Vitals + Symptoms + Medical History
       ↓
Severity Classification
       ↓
Ambulance Priority
```

For example, respiratory emergencies have an increased probability of abnormal oxygen saturation and respiratory distress.

Similarly, neurological emergencies have a greater probability of reduced GCS and altered consciousness.

Trauma cases have increased probabilities of bleeding and injury.

This creates relationships that an ML model can learn rather than simply reproducing arbitrary random numbers.

---

# Dispatch Generation

The dispatch dataset follows a separate simulation process:

```text
Emergency Incident
       ↓
Available Ambulances
       ↓
Distance
       ↓
Traffic
       ↓
Road Condition
       ↓
Travel Speed
       ↓
ETA
       ↓
Ambulance Capability
       ↓
Dispatch Score
       ↓
Best Ambulance
```

The closest ambulance is therefore not necessarily the best ambulance.

For example:

```text
Ambulance A
Distance: 4 km
Traffic: High
ETA: 15 min

Ambulance B
Distance: 6 km
Traffic: Low
ETA: 9 min
```

The system can select Ambulance B despite it being farther away.

---

# Machine Learning Usage

## Model 1 — Emergency Severity

The primary ML task is multiclass classification:

```text
Patient information
        ↓
Severity Model
        ↓
Non-Urgent
Low
Moderate
Emergency
Critical
```

Potential input features include:

- Vital signs
- Symptoms
- Consciousness
- GCS
- Medical history
- Condition
- Injury information

The following should not be used as direct model inputs:

```text
Clinical_Score
Severity
Ambulance_Priority
```

These contain information derived from or directly representing the target.

---

# Model 2 — ETA Prediction

The dispatch dataset can later be used to develop an ETA prediction model.

Potential features:

```text
Distance
Traffic_Level
Road_Condition
Base_Speed_KMH
Ambulance_Type
```

Target:

```text
Predicted_ETA_Minutes
```

The eventual objective is to replace the simulated ETA calculation with an ML-based travel-time prediction system.

---

# Dispatch Optimization

Once severity and ETA models are available, the system can combine them:

```text
Patient Severity
        +
Ambulance Capability
        +
Predicted ETA
        ↓
Dispatch Decision
```

A critical patient should prioritize an appropriate high-capability ambulance while minimizing response time.

---

# Future Routing Layer

The current dataset provides a foundation for a future dynamic routing simulation.

The planned system is:

```text
Patient
   ↓
Severity Prediction
   ↓
Emergency Priority
   ↓
Available Ambulances
   ↓
ETA Prediction
   ↓
Best Ambulance
   ↓
Hospital Selection
   ↓
Route Optimization
   ↓
Live Traffic Update
   ↓
ETA Recalculation
   ↓
Dynamic Rerouting
```

The routing component can eventually use a real road network and simulated or live traffic information.

---

# Important Limitations

This is a **synthetic dataset**.

It is intended for:

- ML development
- algorithm testing
- system simulation
- benchmarking
- prototyping
- demonstration

It must **not** be treated as clinical evidence or used for actual medical decision-making.

The severity labels are generated by simulation logic rather than real clinicians, and the ambulance/hospital locations are simulated.

Model performance on this dataset therefore demonstrates the ability to learn the synthetic environment, **not real-world clinical performance**.

---

# Dataset Version

Current synthetic environment:

```text
Patients:              100,000
Ambulances:              1,000
Hospitals:                 300
Dispatch scenarios:   ~500,000
```

Random seed:

```text
42
```

The random seed is fixed to make dataset generation reproducible.

---

# Project Goal

The ultimate goal of these datasets is to support an end-to-end prototype of an:

> **AI-powered Emergency Ambulance Priority, Dispatch, Hospital Selection, and Dynamic Routing System**

The ML components are responsible for prediction, while the decision and routing layers are responsible for selecting the appropriate ambulance, hospital, and route.