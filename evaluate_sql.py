import asyncio
import json
import os
import time
from dotenv import load_dotenv
from google.api_core import exceptions  

# Import modules
from bi_agent.agent import text_to_sql_runner
from bi_agent.bi_service import BIService
from google.genai import types

from bi_agent.tools import get_database_schema

load_dotenv(dotenv_path='bi_agent/.env')

async def evaluate():
    print("🚀 Starting Evaluation (Safety Mode: Ultra Slow)...")
    
    # ... (ส่วน connect db เหมือนเดิม) ...
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

    try:
        with open('evaluation_set.json', 'r') as f:
            test_cases = json.load(f)
    except:
        print("❌ No evaluation_set.json found")
        return

    score = 0
    total = len(test_cases)
    schema_context = get_database_schema()
    for i, case in enumerate(test_cases):
        print(f"\n[{i+1}/{total}] 🔹 Question: {case['question']}")
        
        # 🛡️ พักยาวๆ 30 วินาที ก่อนเริ่มข้อใหม่ (Free Tier ต้องใจเย็น)
        print("   💤 Cooling down (30s)... ", end="", flush=True)
        # แบ่งรอทีละนิดเพื่อให้กด Ctrl+C หยุดได้ถ้าต้องการ
        for _ in range(30):
            await asyncio.sleep(1)
            print(".", end="", flush=True)
        print(" Go!")

        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                # สร้าง Session ใหม่
                session = await text_to_sql_runner.session_service.create_session(
                    user_id='test_user', app_name='text_to_sql'
                )

                enhanced_prompt = f"""Here is the Database Schema you must use:{schema_context}User Question: {case['question']}"""
                content = types.Content(role='user', parts=[types.Part(text=enhanced_prompt)])
 
                # รัน Agent
                events = text_to_sql_runner.run_async(user_id='test_user', session_id=session.id, new_message=content)
                
                generated_sql = ""
                async for event in events:
                    if event.actions and event.actions.state_delta:
                        generated_sql = event.actions.state_delta.get('sql_query', '')
                
                # ถ้าผ่านมาถึงตรงนี้แปลว่าไม่ Error -> หลุด loop retry
                break 

            except Exception as e:
                # เช็คว่าเป็น Error 429 หรือไม่
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    retry_count += 1
                    wait_time = retry_count * 20 # รอเพิ่มขึ้นเรื่อยๆ 20s, 40s, 60s
                    print(f"\n   ⚠️ Hit Rate Limit! Retrying in {wait_time}s... (Attempt {retry_count}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"   ❌ Agent Error: {e}")
                    generated_sql = "" # Error อื่นที่ไม่ใช่ Rate Limit ให้ข้ามเลย
                    break

        if not generated_sql:
            print("   ⚠️ No SQL returned or Failed after retries")
            continue

        # ... (ส่วนตรวจคำตอบ เหมือนเดิม) ...
        # Clean SQL
        generated_sql = generated_sql.replace("```sql", "").replace("```", "").strip()
        print(f"   🤖 Generated SQL: {generated_sql}")
        
        # ... (Run SQL check logic) ...
        # (Copy Logic เดิมมาใส่ตรงนี้ได้เลยครับ)
        # ---------------------------------------------------
        try:
             res_gen = db_service.execute_sql(generated_sql)
             res_truth = db_service.execute_sql(case['ground_truth_sql'])
             
             if res_gen['success'] and res_truth['success']:
                if res_gen['data'].equals(res_truth['data']):
                    print("   ✅ CORRECT")
                    score += 1
                else:
                    print("   ❌ INCORRECT (Data mismatch)")
             else:
                print(f"   ❌ SQL Execution Error: {res_gen.get('error', 'Unknown')}")
        except Exception as db_err:
             print(f"   ❌ DB Check Error: {db_err}")
        # ---------------------------------------------------

    print(f"\n🎯 Final Score: {score}/{total}")
    db_service.close()

if __name__ == "__main__":
    asyncio.run(evaluate())