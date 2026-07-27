import os
import random
import json
from flask import Flask, render_template, request, jsonify
from groq import Groq
from dotenv import load_dotenv

# Initialize environment configurations
load_dotenv()

app = Flask(__name__, template_folder='../templates')

# Initialize Groq client with standard environment variable lookup
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
client = None
if GROQ_API_KEY:
    client = Groq(api_key=GROQ_API_KEY)

# Initialize Supabase authentication configuration parameters
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_KEY", ""))

supabase_client = None
if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception as e:
        print(f"Supabase client initialization note: {e}")

# US Hospital Case Archetypes for Simulation Data
STANDARD_COMPLAINTS = [
    {"complaint": "Crushing retrosternal chest pain radiating to left jaw, diaphoresis", "vitals": "BP: 165/102, HR: 112, RR: 24, SpO2: 91%", "base_age": (45, 80)},
    {"complaint": "Accidental ingestion of unknown quantity of acetaminophen liquid by toddler", "vitals": "BP: 90/60, HR: 135, RR: 28, SpO2: 98%", "base_age": (1, 4)},
    {"complaint": "Deep 8cm jagged laceration on right forearm with active pulsatile bleeding", "vitals": "BP: 105/65, HR: 118, RR: 22, SpO2: 99%", "base_age": (18, 60)},
    {"complaint": "Productive cough, fever of 103.1°F, worsening dyspnea, crackles in right lower lobe", "vitals": "BP: 118/75, HR: 98, RR: 26, SpO2: 93%", "base_age": (65, 90)},
    {"complaint": "Suspected opioid overdose; found unresponsive with pinpoint pupils and shallow breathing", "vitals": "BP: 95/55, HR: 58, RR: 6, SpO2: 82%", "base_age": (20, 45)},
    {"complaint": "Mild inversion ankle injury during sports activity, local edema, able to bear weight partially", "vitals": "BP: 120/80, HR: 72, RR: 14, SpO2: 99%", "base_age": (12, 30)},
    {"complaint": "Superficial chemical splash to left forearm, localized erythema, mild burning pain", "vitals": "BP: 125/82, HR: 80, RR: 16, SpO2: 100%", "base_age": (22, 55)},
    {"complaint": "Acute onset of left-sided facial droop, right arm weakness, and slurred speech", "vitals": "BP: 188/110, HR: 88, RR: 18, SpO2: 96%", "base_age": (55, 85)}
]

CRISIS_COMPLAINTS = [
    {"complaint": "Mass Casualty Event: Penetrating shrapnel injury to upper torso, active hemorrhage, signs of tension pneumothorax", "vitals": "BP: 80/40, HR: 140, RR: 35, SpO2: 85%", "base_age": (18, 40)},
    {"complaint": "Mass Casualty Event: Severe inhalation injury from industrial fire, soot in oral cavity, stridor", "vitals": "BP: 130/85, HR: 120, RR: 32, SpO2: 88%", "base_age": (25, 60)},
    {"complaint": "Mass Casualty Event: Crush syndrome with bilateral lower extremity entrapment, absent distal pulses", "vitals": "BP: 90/50, HR: 125, RR: 26, SpO2: 92%", "base_age": (19, 50)},
    {"complaint": "Mass Casualty Event: Blunt head trauma, GCS 7, unequal sluggish pupils following structural collapse", "vitals": "BP: 170/95, HR: 50, RR: 10, SpO2: 90%", "base_age": (10, 70)}
]

US_NAMES = ["Emma Smith", "Liam Johnson", "Olivia Williams", "Noah Brown", "Sophia Jones", 
            "Jackson Miller", "Ava Davis", "Lucas Garcia", "Isabella Rodriguez", "Ethan Wilson"]

# In-memory fallback store for physician-entered diagnoses, keyed by patient_id.
# Used when Supabase credentials are not configured, mirroring the mock-fallback
# pattern already used elsewhere for triage and vision.
DIAGNOSIS_STORE = {}

@app.route('/')
@app.route('/index')
def index():
    """Renders the single-page Glassmorphic Clinical Dashboard front-end configuration."""
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def get_config():
    """Exposes public client authentication configuration parameters for Supabase integration."""
    return jsonify({
        "supabase_url": SUPABASE_URL,
        "supabase_anon_key": SUPABASE_ANON_KEY
    })

@app.route('/api/triage', methods=['POST'])
def handle_triage():
    """
    Generates realistic randomized clinical data and passes it to Groq for ESI sorting
    and bio-resource allocation matching optimization.
    """
    try:
        data = request.json or {}
        inventory = data.get("inventory", {
            "Acetaminophen": 100,
            "Ibuprofen": 100,
            "Amoxicillin": 50,
            "Azithromycin": 50,
            "Epinephrine": 10,
            "Morphine Sulfate": 20
        })
        crisis_mode = data.get("crisis_mode", False)
        
        # Build evaluation sample batch
        patient_count = random.randint(7, 10) if not crisis_mode else 10
        selected_patients = []
        
        for i in range(patient_count):
            if crisis_mode and random.random() > 0.3:
                archetype = random.choice(CRISIS_COMPLAINTS)
            else:
                archetype = random.choice(STANDARD_COMPLAINTS)
                
            age = random.randint(archetype["base_age"][0], archetype["base_age"][1])
            name = random.choice(US_NAMES) + f" {chr(65 + random.randint(0,25))}."
            
            selected_patients.append({
                "patient_id": f"PT-{1000 + i}",
                "name": name,
                "age": age,
                "chief_complaint": archetype["complaint"],
                "vitals": archetype["vitals"]
            })

        # Return mock structures directly if no remote credentials exist
        if not client:
            return jsonify(generate_mock_triage(selected_patients, inventory))

        # Groq Reasoning Prompt construction mapping to active 2026 models
        prompt = f"""
        You are an expert AI/ML Clinical Solutions Architect operating within a US hospital emergency medicine infrastructure.
        Perform Emergency Severity Index (ESI) Triage (Levels 1: Resuscitation to 5: Non-Urgent), allocate immediate medications, and construct a long-term clinical prognosis.

        Input Patients:
        {json.dumps(selected_patients, indent=2)}

        Available Medication Stock Sliders:
        {json.dumps(inventory, indent=2)}

        Constraints & Guidelines:
        1. Classify ESI Level based strictly on vital signs and objective physiological severity.
        2. Assign a matching color_code string: ESI 1 = "red", ESI 2 = "orange", ESI 3 = "yellow", ESI 4 = "green", ESI 5 = "blue".
        3. Match a drug from inventory. If the primary drug choice is depleted or running dangerously low, trigger an Automated Cross-Formulation Drug Matcher alert substituting an alternative compound safely matching US medical alternatives.
        4. Synthesize a detailed "prognosis_outlook" outlining expected clinical timeline over the coming years, anticipated symptoms (noting abnormal warning signals to monitor), care plans (treatment, physical rehab, or specialist therapies), and secondary medications likely to be used over the life of the recovery/disease management.
        5. Calculate a Bio-Resource sustainability_score (0-100) indicating total emergency room inventory health.
        6. Return ONLY a valid JSON object matching the output schema structure perfectly. Do not add conversational text or markdown blocks.

        Output Schema Template:
        {{
          "triage_queue": [
            {{
              "patient_id": "string",
              "name": "string",
              "age": integer,
              "chief_complaint": "string",
              "vitals": "string",
              "esi_level": integer,
              "color_code": "string",
              "allocated_resource": "string",
              "clinical_justification": "string",
              "prognosis_outlook": {{
                "expected_duration": "string",
                "long_term_expectations": "string",
                "treatment_plan": "string",
                "recommended_medications": ["string"]
              }}
            }}
          ],
          "resource_analysis": {{
            "sustainability_score": integer,
            "cross_formulation_alerts": ["string"],
            "inventory_status": {{
               "MedicationName": "Stable" or "Low" or "Critical"
            }}
          }}
        }}
        """

        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3
        )

        response_content = completion.choices[0].message.content
        parsed_result = json.loads(response_content)
        
        # Sort queue on server side to guarantee priority sequence (ESI 1 first)
        parsed_result["triage_queue"] = sorted(parsed_result["triage_queue"], key=lambda x: x.get("esi_level", 5))
        return jsonify(parsed_result)

    except Exception as e:
        return jsonify({"error": str(e), "status": "malformed_inference_execution"}), 500

@app.route('/api/vision', methods=['POST'])
def handle_vision():
    """
    Accepts Base64 clinical image data payloads, routing them to the Qwen 3.6 Multimodal 
    vision array for emergency condition tracking and marker evaluations.
    """
    try:
        data = request.json or {}
        image_base64 = data.get("image")
        phase = data.get("phase", "identification") # identification vs healing_progress

        if not image_base64:
            return jsonify({"error": "Missing clinical payload parameter: image"}), 400

        if not client:
            return jsonify(generate_mock_vision(phase))

        # Build clean inline multimodal content layout for Groq Vision execution
        prompt_text = f"""
        Analyze this clinical dermatological/wound matrix image for a US healthcare setting.
        Current operational tracking phase: {phase.upper()}

        Provide a structured evaluation in raw JSON text matching the target schema perfectly.
        
        Output Target Schema:
        {{
          "severity_tier": "Non-Urgent" or "Urgent" or "Emergent",
          "educational_explanation": "Provide clean educational overview safely isolated from specific absolute dynamic diagnoses.",
          "tissue_regeneration_metric": integer (from 0 to 100 representing healing efficiency index),
          "infection_flags": ["string alert description"],
          "visual_markers": ["string indicator details"]
        }}
        """

        completion = client.chat.completions.create(
            model="qwen/qwen3.6-27b",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )

        parsed_vision = json.loads(completion.choices[0].message.content)
        return jsonify(parsed_vision)

    except Exception as e:
        return jsonify({"error": str(e), "status": "malformed_vision_execution"}), 500

@app.route('/api/diagnosis', methods=['POST'])
def save_diagnosis():
    """
    Allows the attending physician to upload/save a formal diagnosis and care plan
    for a given patient. Persists to Supabase when configured, otherwise falls back
    to the in-memory DIAGNOSIS_STORE for the lifetime of the process.
    """
    try:
        data = request.json or {}
        patient_id = data.get("patient_id")
        diagnosis_text = (data.get("diagnosis_text") or "").strip()
        care_plan = (data.get("care_plan") or "").strip()
        physician_name = (data.get("physician_name") or "Attending Physician").strip()

        if not patient_id or not diagnosis_text:
            return jsonify({"error": "patient_id and diagnosis_text are required"}), 400

        record = {
            "patient_id": patient_id,
            "diagnosis_text": diagnosis_text,
            "care_plan": care_plan,
            "physician_name": physician_name
        }

        if supabase_client:
            try:
                supabase_client.table("diagnoses").upsert(record).execute()
            except Exception as e:
                print(f"Supabase diagnosis upsert note: {e}")
                DIAGNOSIS_STORE[patient_id] = record
        else:
            DIAGNOSIS_STORE[patient_id] = record

        return jsonify({"status": "saved", "diagnosis": record})

    except Exception as e:
        return jsonify({"error": str(e), "status": "diagnosis_save_failed"}), 500

@app.route('/api/diagnosis', methods=['GET'])
def get_diagnosis():
    """Retrieves the saved diagnosis/care plan for a given patient_id."""
    try:
        patient_id = request.args.get("patient_id")
        if not patient_id:
            return jsonify({"error": "patient_id query parameter is required"}), 400

        record = None
        if supabase_client:
            try:
                res = supabase_client.table("diagnoses").select("*").eq("patient_id", patient_id).limit(1).execute()
                if res.data:
                    record = res.data[0]
            except Exception as e:
                print(f"Supabase diagnosis fetch note: {e}")

        if record is None:
            record = DIAGNOSIS_STORE.get(patient_id)

        return jsonify({"diagnosis": record})

    except Exception as e:
        return jsonify({"error": str(e), "status": "diagnosis_fetch_failed"}), 500

@app.route('/api/diagnosis-chat', methods=['POST'])
def diagnosis_chat():
    """
    Care Plan Assistant: answers family/patient questions about a specific diagnosis
    and its associated care plan in a medically formal but plain-language tone.
    Grounds every answer strictly in the physician-entered diagnosis/care plan text
    so it never invents clinical facts beyond what the attending physician recorded.
    """
    try:
        data = request.json or {}
        patient_id = data.get("patient_id")
        question = (data.get("question") or "").strip()

        if not question:
            return jsonify({"error": "question is required"}), 400

        record = None
        if patient_id:
            if supabase_client:
                try:
                    res = supabase_client.table("diagnoses").select("*").eq("patient_id", patient_id).limit(1).execute()
                    if res.data:
                        record = res.data[0]
                except Exception as e:
                    print(f"Supabase diagnosis fetch note: {e}")
            if record is None:
                record = DIAGNOSIS_STORE.get(patient_id)

        diagnosis_text = (record or {}).get("diagnosis_text", "")
        care_plan = (record or {}).get("care_plan", "")

        if not diagnosis_text:
            return jsonify({
                "answer": "No formal diagnosis has been uploaded for this patient yet. Please ask the attending physician to record the diagnosis and care plan before questions can be answered here."
            })

        if not client:
            return jsonify(generate_mock_diagnosis_chat_answer(question))

        system_prompt = f"""
        You are a Clinical Care Plan Assistant embedded in a hospital patient portal.
        Your role is to help patients and their family members understand a specific
        physician-recorded diagnosis and care plan.

        Diagnosis on record:
        {diagnosis_text}

        Care Plan on record:
        {care_plan if care_plan else "No separate care plan notes were recorded."}

        Guidelines:
        1. Maintain a medically formal, serious, and professional tone at all times.
        2. Use plain language a family member without medical training can understand;
           briefly define any clinical term you must use.
        3. Answer only using the diagnosis and care plan text provided above. Do not
           invent test results, medications, or prognoses that are not stated there.
        4. If the question cannot be answered from the information on record, say so
           clearly and advise the family to speak directly with the attending physician
           or care team rather than speculating.
        5. Do not provide instructions that could be used to alter dosages or treatment
           without clinician oversight; encourage contacting the care team for any
           urgent or changing symptoms.
        6. Keep answers concise and organized, using short paragraphs or a short list
           when helpful.
        """

        completion = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            temperature=0.3
        )

        answer = completion.choices[0].message.content
        return jsonify({"answer": answer})

    except Exception as e:
        return jsonify({"error": str(e), "status": "diagnosis_chat_failed"}), 500

def generate_mock_diagnosis_chat_answer(question):
    """Resilient fallback response when no Groq credentials are configured."""
    return {
        "answer": (
            "Based on the diagnosis and care plan recorded by the attending physician, "
            "this appears to be a stable, actively monitored condition. In general terms, "
            "the care team's plan focuses on symptom management, scheduled follow-up, and "
            "watching for any warning signs noted in the record. For specifics about your "
            "question, or for anything that feels urgent, please speak directly with the "
            "attending physician or nursing staff, as this assistant can only summarize "
            "what has already been documented."
        )
    }

def generate_mock_triage(patients, inventory):
    """Resilient computational fallback function producing high-fidelity structural mock data."""
    queue = []
    alerts = []
    
    # Check for low inventory levels locally to trigger alerts
    for key, val in inventory.items():
        if int(val) <= 15:
            alerts.append(f"Automated Matrix Alert: {key} stock level is low. Initiated cross-formulation substitute lookup.")

    for p in patients:
        # Simplistic ESI assignment rule based on clinical indicators
        complaint_lower = p["chief_complaint"].lower()
        
        # Default mock prognosis dictionary structure
        prog = {
            "expected_duration": "3-6 weeks",
            "long_term_expectations": "Gradual resolution of acute symptoms. Monitor for localized irritation, abnormal persistent swelling, or sudden fever spikes.",
            "treatment_plan": "Scheduled clinical follow-up within 14 days, rest, hydration, and progressive rehabilitation exercises.",
            "recommended_medications": ["Acetaminophen", "Ibuprofen"]
        }

        if "chest pain" in complaint_lower or "overdose" in complaint_lower or "shrapnel" in complaint_lower:
            esi = 1
            color = "red"
            res = "Epinephrine" if "overdose" not in complaint_lower else "Morphine Sulfate"
            just = "Immediate threat to physiological life signs detected. Requires instant critical room entry."
            
            if "chest pain" in complaint_lower:
                prog = {
                    "expected_duration": "Lifelong chronic cardiovascular management",
                    "long_term_expectations": "Increased risk of coronary artery complications. Monitor for abnormal radiating pressure, persistent dyspnea, or sudden diaphoresis.",
                    "treatment_plan": "Immediate cardiology consultation, cardiac catheterization/angiography, strict low-sodium cardiac diet, and supervised cardiac rehab.",
                    "recommended_medications": ["Aspirin", "Beta-blockers (Metoprolol)", "Statins (Atorvastatin)", "Nitroglycerin as needed"]
                }
            elif "overdose" in complaint_lower:
                prog = {
                    "expected_duration": "Indefinite clinical recovery and support phase",
                    "long_term_expectations": "Risk of recurring respiratory depression or permanent hypoxia-related cognitive issues. Monitor for abnormal drowsiness, bradycardia, or shallow breathing.",
                    "treatment_plan": "Continuous monitoring for 4-6 hours post-emergency, toxicological psychiatric evaluation, substance abuse outpatient program, and family education on rescue kits.",
                    "recommended_medications": ["Naloxone (on-hand rescue spray)", "Buprenorphine or Methadone maintenance therapy"]
                }
            else: # shrapnel
                prog = {
                    "expected_duration": "6-12 months recovery and structural remodeling",
                    "long_term_expectations": "Prolonged localized tissue healing, risk of delayed wound contraction or deep structural infection. Monitor for abnormal malodorous discharge, high fever, or loss of limb sensation.",
                    "treatment_plan": "Surgical irrigation & debridement, sterile wound vacuum maintenance, physical/occupational rehabilitation to recover distal functions, and periodic serial imaging.",
                    "recommended_medications": ["Broad-spectrum IV/Oral Antibiotics", "Analgesics (Morphine/Tramadol)", "Tetanus toxoid booster"]
                }
                
        elif "bleeding" in complaint_lower or "laceration" in complaint_lower or "inhalation" in complaint_lower:
            esi = 2
            color = "orange"
            res = "Morphine Sulfate"
            just = "High risk scenario. Severe pain or complex structural risk present."
            
            if "inhalation" in complaint_lower:
                prog = {
                    "expected_duration": "3-6 months dynamic pulmonary recovery",
                    "long_term_expectations": "Reactive bronchospasm, risk of delayed chemical pneumonitis or airway stenosis. Monitor for abnormal stridor, severe persistent dry cough, or oxygen desaturation below 90%.",
                    "treatment_plan": "Inpatient pulmonary ICU observation, daily spirometry mapping, high-flow humidified oxygen therapy, and avoidance of any gaseous airway irritants.",
                    "recommended_medications": ["Bronchodilators (Albuterol)", "Systemic/Inhaled Corticosteroids (Prednisone)"]
                }
            else: # laceration
                prog = {
                    "expected_duration": "4-8 weeks acute tissue healing",
                    "long_term_expectations": "Progressive scar tissue remodeling and transient localized stiffness. Monitor for abnormal purulent wound discharge, severe peripheral paresthesia, or loss of capillary refill.",
                    "treatment_plan": "Suture/staple integrity checks, removal in 10-14 days, strict daily sterile dressing changes, and progressive range-of-motion stretching.",
                    "recommended_medications": ["First-generation Cephalosporins (Cephalexin)", "OTC Pain Relievers"]
                }
                
        elif "cough" in complaint_lower or "fever" in complaint_lower:
            esi = 3
            color = "yellow"
            res = "Amoxicillin" if int(inventory.get("Amoxicillin", 0)) > 10 else "Azithromycin"
            if int(inventory.get("Amoxicillin", 0)) <= 10:
                alerts.append("Cross-Formulation Triggered: Amoxicillin depleted. Substituted Azithromycin for respiratory infection.")
            just = "Systemic response indicated. Stable vitals but demands investigative diagnostic assays."
            
            prog = {
                "expected_duration": "2-4 weeks",
                "long_term_expectations": "Gradual clearance of pulmonary consolidations. Monitor for abnormal dyspnea, persistent high fevers, or localized pleuritic pain.",
                "treatment_plan": "Complete full antibiotic regimen, rest, hydration, daily incentive spirometry, and repeat chest X-ray in 4-6 weeks to verify total clearance.",
                "recommended_medications": ["Amoxicillin or Azithromycin", "Mucolytics (Guaifenesin)", "Antipyretics"]
            }
            
        else:
            esi = 4
            color = "green"
            res = "Acetaminophen"
            just = "Stable localized signs. Evaluation timing flexible around major triage flow queues."
            
            if "ankle" in complaint_lower:
                prog = {
                    "expected_duration": "4-6 weeks ligamentous stabilization",
                    "long_term_expectations": "Transient edema and partial weight-bearing limitations. Monitor for abnormal chronic joint instability, persistent clicking, or localized deep vein thrombosis signs.",
                    "treatment_plan": "Rest, Ice, Compression, Elevation (RICE) protocol, physical therapy with focus on proprioception, and supportive ankle bracing during high-impact sports.",
                    "recommended_medications": ["NSAIDs (Ibuprofen/Naproxen)"]
                }
            elif "chemical splash" in complaint_lower:
                prog = {
                    "expected_duration": "1-3 weeks epidermal recovery",
                    "long_term_expectations": "Local inflammation and risk of post-inflammatory hyperpigmentation. Monitor for abnormal deep blister formation, expanding erythema, or necrotic margins.",
                    "treatment_plan": "Immediate continuous irrigation, thin applications of protective petroleum jelly, daily sterile dressings, and avoidance of direct sunlight/UV exposure.",
                    "recommended_medications": ["Silver Sulfadiazine cream", "Oral Antihistamines for pruritus"]
                }
            elif "facial droop" in complaint_lower or "speech" in complaint_lower:
                prog = {
                    "expected_duration": "6-24 months neurologic recovery and rehabilitation",
                    "long_term_expectations": "Deficits in motor control or cognitive speech. Monitor for abnormal sudden unilateral weakness, sensory numbness, worsening dysphagia, or severe sudden cephalalgia.",
                    "treatment_plan": "Stat CT head scan, swallow evaluation, stroke ICU protocols, occupational and physical therapies, speech therapy, and continuous neurologic reassessments.",
                    "recommended_medications": ["Antiplatelets (Aspirin/Clopidogrel)", "Statins (Rosuvastatin)", "Antihypertensive agents"]
                }

        p_copy = p.copy()
        p_copy.update({
            "esi_level": esi,
            "color_code": color,
            "allocated_resource": res,
            "clinical_justification": just,
            "prognosis_outlook": prog
        })
        queue.append(p_copy)

    queue = sorted(queue, key=lambda x: x["esi_level"])
    
    status_map = {}
    for key, val in inventory.items():
        v = int(val)
        status_map[key] = "Stable" if v > 40 else ("Low" if v > 15 else "Critical")

    return {
        "triage_queue": queue,
        "resource_analysis": {
            "sustainability_score": max(20, 100 - (len(alerts) * 12)),
            "cross_formulation_alerts": list(set(alerts)) if alerts else ["All resource allocations operating inside normal thresholds."],
            "inventory_status": status_map
        }
    }

def generate_mock_vision(phase):
    """Resilient diagnostic simulation matrix matching identification vs tracking cycles."""
    if phase == "identification":
        return {
            "severity_tier": "Urgent",
            "educational_explanation": "Preliminary tissue metrics suggest an active inflammatory disruption consistent with epidermal degradation or deep dermal incision parameters.",
            "tissue_regeneration_metric": 35,
            "infection_flags": ["Elevated erythema present at peripheral boundaries", "No systemic necrosis verified"],
            "visual_markers": ["Disrupted stratum corneum", "Fibrinous exudate tracking across wound center"]
        }
    else:
        return {
            "severity_tier": "Non-Urgent",
            "educational_explanation": "Comparative analysis mapping shows clear reduction in local acute inflammation alongside progressive architectural healing loops.",
            "tissue_regeneration_metric": 82,
            "infection_flags": ["Zero active purulent collections", "Peripheral erythema fully resolved"],
            "visual_markers": ["Robust granulation matrix establishing baseline surface", "Active edge migration showing re-epithelialization"]
        }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))