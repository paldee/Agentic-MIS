import asyncio
import json
import os
import pandas as pd
from dotenv import load_dotenv

# Import modules (อ้างอิงตามโครงสร้างโปรเจกต์ของคุณ)
from bi_agent.agent import text_to_sql_runner
from bi_agent.bi_service import BIService
from google.genai import types
from bi_agent.tools import get_database_schema

load_dotenv(dotenv_path='bi_agent/.env')

def compare_dataframes(df_gen, df_truth):

    try:
        if df_gen is None or df_truth is None:
            return False
        
        # 1. ถ้าจำนวนแถวหรือคอลัมน์ไม่เท่ากัน ผิดแน่นอน
        if df_gen.shape != df_truth.shape:
            return False

        # 2. Copy ข้อมูลออกมาเพื่อไม่ให้กระทบตัวแปรเดิม
        dg = df_gen.copy()
        dt = df_truth.copy()

        # 3. Normalize ชื่อคอลัมน์ (ป้องกันปัญหาเรื่อง Alias เช่น Total_Revenue vs SUM(Revenue))
        dg.columns = [f"col_{i}" for i in range(len(dg.columns))]
        dt.columns = [f"col_{i}" for i in range(len(dt.columns))]

        # 4. จัดการเรื่องทศนิยม (Rounding) ป้องกันปัญหา Float precision (เช่น 10.0000001 vs 10.0)
        dg = dg.round(4)
        dt = dt.round(4)

        # 5. Sort ข้อมูลตามทุกคอลัมน์และ Reset Index (ป้องกันปัญหาการสลับแถว)
        dg = dg.sort_values(by=list(dg.columns)).reset_index(drop=True)
        dt = dt.sort_values(by=list(dt.columns)).reset_index(drop=True)

        # 6. เปรียบเทียบข้อมูลข้างใน
        return dg.equals(dt)
    except Exception as e:
        print(f"   ⚠️ Comparison Error: {e}")
        return False

async def evaluate():
    print("🚀 Starting Evaluation (Safety Mode: Professional Logic)...")
    
    # 1. Database Connection
    db_service = BIService(
        server=os.getenv("MSSQL_SERVER"),
        database=os.getenv("MSSQL_DATABASE"),
        username=os.getenv("MSSQL_USERNAME"),
        password=os.getenv("MSSQL_PASSWORD")
    )
    connected, msg = db_service.connect()
    if not connected:
        print(f"❌ DB Connect Fail: {msg}")
        return

    # 2. Load Test Cases
    try:
        with open('evaluation_set.json', 'r', encoding='utf-8') as f:
            test_cases = json.load(f)
    except FileNotFoundError:
        print("❌ No evaluation_set.json found")
        return

    score = 0
    total = len(test_cases)
    schema_context = get_database_schema()

    for i, case in enumerate(test_cases):
        print(f"\n[{i+1}/{total}] 🔹 Question: {case['question']}")
        
        # 🛡️ Cooling down (Free Tier Safety)
        print("   💤 Cooling down (30s)... ", end="", flush=True)
        for _ in range(30):
            await asyncio.sleep(1)
            print(".", end="", flush=True)
        print(" Go!")

        retry_count = 0
        max_retries = 3
        generated_sql = ""
        
        while retry_count < max_retries:
            try:
                # สร้าง Session ใหม่สำหรับแต่ละข้อ
                session = await text_to_sql_runner.session_service.create_session(
                    user_id='test_user', app_name='text_to_sql'
                )

                enhanced_prompt = f"Here is the Database Schema:\n{schema_context}\n\nUser Question: {case['question']}"
                content = types.Content(role='user', parts=[types.Part(text=enhanced_prompt)])

                # รัน Agent ดึงผลลัพธ์
                events = text_to_sql_runner.run_async(user_id='test_user', session_id=session.id, new_message=content)
                
                async for event in events:
                    if event.actions and event.actions.state_delta:
                        generated_sql = event.actions.state_delta.get('sql_query', '')
                
                if generated_sql:
                    break 

            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    retry_count += 1
                    wait_time = retry_count * 20
                    print(f"\n   ⚠️ Hit Rate Limit! Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"   ❌ Agent Error: {e}")
                    break

        if not generated_sql:
            print("   ⚠️ No SQL returned or Failed after retries")
            continue

        # Clean SQL String
        clean_sql = generated_sql.replace("```sql", "").replace("```", "").strip()
        print(f"   🤖 Generated SQL: {clean_sql}")
        
        # 3. Check Results (The Core Logic)
        try:
            res_gen = db_service.execute_sql(clean_sql)
            res_truth = db_service.execute_sql(case['ground_truth_sql'])
            
            if res_gen['success'] and res_truth['success']:
                # ใช้ฟังก์ชันเปรียบเทียบระดับโปรที่เราเขียนไว้
                is_correct = compare_dataframes(res_gen['data'], res_truth['data'])
                
                if is_correct:
                    print("   ✅ CORRECT")
                    score += 1
                else:
                    print("   ❌ INCORRECT (Data mismatch or Column name issue)")
                    # Debug: พิมพ์ออกมาดูว่าต่างกันตรงไหน
                    # print(f"Generated Data:\n{res_gen['data'].head(2)}")
                    # print(f"Truth Data:\n{res_truth['data'].head(2)}")
            else:
                err_msg = res_gen.get('error', 'Unknown Error')
                print(f"   ❌ SQL Execution Error: {err_msg}")

        except Exception as db_err:
             print(f"   ❌ DB Check Error: {db_err}")
    # 4. Final Summary
    print("-" * 30)
    print(f"🎯 Final Accuracy Score: {score}/{total} ({(score/total)*100:.2f}%)")
    print("-" * 30)
    db_service.close()

if __name__ == "__main__":
    asyncio.run(evaluate())