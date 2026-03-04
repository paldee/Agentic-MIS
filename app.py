"""
Gradio UI for the Business Intelligence Agent Pipeline.
Optimized Hybrid Architecture with Custom UI & Random Loading GIFs.
"""

import gradio as gr
import asyncio
import os
import pandas as pd
import altair as alt
import json
import random
from dotenv import load_dotenv
from google.genai import types

# 🚀 นำเข้าเครื่องมือที่เร็วกว่า (ไม่ใช้ root_runner แล้ว)
from bi_agent.tools import execute_sql_and_format, get_database_schema
from bi_agent.agent import text_to_sql_runner, analysis_runner

# Load environment variables from bi_agent/.env
load_dotenv(dotenv_path='bi_agent/.env')

# ============================================================================
# 🏎️ Heuristic Fast Track Logic (ทางด่วนวาดกราฟด้วย Python)
# ============================================================================
def get_heuristic_analysis(df: pd.DataFrame):
    if df.empty:
        return None, None
        
    cols = df.columns
    if len(cols) == 2 and len(df) <= 20:
        col0_test = pd.to_numeric(df[cols[0]], errors='coerce')
        col1_test = pd.to_numeric(df[cols[1]], errors='coerce')
        
        is_num_0 = col0_test.notna().all()
        is_num_1 = col1_test.notna().all()
        
        if is_num_0 != is_num_1:
            dim = cols[1] if is_num_0 else cols[0]
            val = cols[0] if is_num_0 else cols[1]
            
            chart_spec = f"""
chart = alt.Chart(df).mark_bar().encode(
    x=alt.X('{val}:Q'),
    y=alt.Y('{dim}:N', sort='-x', title=None),
    tooltip=['{dim}', '{val}']
).properties(title='{val} by {dim}').interactive()
"""
            top_row = df.sort_values(by=val, ascending=False).iloc[0]
            val_formatted = f"{top_row[val]:,.2f}" if isinstance(top_row[val], float) else f"{top_row[val]}"
            explanation = f"The highest `{dim}` is **{top_row[dim]}** with a total `{val}` of {val_formatted}."
            
            return chart_spec, explanation

    if len(df) == 1 and len(cols) > 1:
        if all(pd.to_numeric(df[c], errors='coerce').notna().all() for c in cols):
            chart_spec = """
df_melted = df.melt(var_name='Metric', value_name='Value')
base = alt.Chart(df_melted).encode(x='Value:Q', y=alt.Y('Metric:N', title=None, sort='-x'))
bars = base.mark_bar()
text = base.mark_text(align='left', dx=5).encode(text='Value:Q')
chart = (bars + text).properties(title='Key Metrics Overview').interactive()
"""
            explanation = "⚡️ **Fast Analysis:** The chart displays the key metrics from your query for direct comparison."
            return chart_spec, explanation
            
    return None, None


# ============================================================================
# 🧠 Pipeline Logic (Hybrid)
# ============================================================================
async def run_bi_pipeline_async(user_question: str):
    results = {}
    
    # --- STEP 1: Text-to-SQL (AI) ---
    print("🤖 1. Generating SQL...")
    session_sql = await text_to_sql_runner.session_service.create_session(user_id='user', app_name='text_to_sql')
    
    schema_context = get_database_schema()
    enhanced_prompt = f"Here is the Database Schema you must use:\n{schema_context}\n\nUser Question: {user_question}"
    content_sql = types.Content(role='user', parts=[types.Part(text=enhanced_prompt)])
    
    events_sql = text_to_sql_runner.run_async(user_id='user', session_id=session_sql.id, new_message=content_sql)
    
    sql_query = ""
    async for event in events_sql:
        if event.actions and event.actions.state_delta:
            if 'sql_query' in event.actions.state_delta:
                sql_query = event.actions.state_delta['sql_query']
    results['sql_query'] = sql_query

    # --- STEP 2: Execute SQL (Python) ---
    print("⚡️ 2. Executing SQL (Python)...")
    if sql_query:
        clean_sql = sql_query.replace("```sql", "").replace("```", "").strip()
        query_results_json = execute_sql_and_format(clean_sql)
        results['query_results'] = query_results_json
    else:
        return results

    # --- STEP 2.5: Heuristic Fast Track ---
    try:
        data_dict = json.loads(query_results_json)
        if data_dict.get('success') and data_dict.get('data'):
            df_temp = pd.DataFrame(data_dict['data'])
            fast_chart_spec, fast_explanation = get_heuristic_analysis(df_temp)
            
            if fast_chart_spec and fast_explanation:
                print("🚀 FAST TRACK: Using Python to generate chart (Skipping AI!)")
                results['chart_spec'] = fast_chart_spec
                results['explanation_text'] = fast_explanation
                return results 
    except Exception as e:
        print(f"Heuristic bypass failed: {e}")

    # --- STEP 3: Unified Analysis (AI) ---
    print("🎨 3. Complex Data. Analyzing with AI...")
    session_viz = await analysis_runner.session_service.create_session(user_id='user', app_name='analysis')
    
    viz_prompt = f"Analyze this data:\n{results['query_results']}"
    content_viz = types.Content(role='user', parts=[types.Part(text=viz_prompt)])
    
    events_viz = analysis_runner.run_async(user_id='user', session_id=session_viz.id, new_message=content_viz)
    
    async for event in events_viz:
        if event.actions and event.actions.state_delta:
            if 'analysis_result' in event.actions.state_delta:
                raw_output = event.actions.state_delta['analysis_result']
                try:
                    clean_output = raw_output.replace("```json", "").replace("```", "").strip()
                    start_index = clean_output.find('{')
                    end_index = clean_output.rfind('}') + 1
                    if start_index != -1 and end_index != -1:
                        json_str = clean_output[start_index:end_index]
                        analysis_data = json.loads(json_str)
                        results['chart_spec'] = analysis_data.get('chart_spec', '')
                        results['explanation_text'] = analysis_data.get('explanation', '')
                    else:
                        results['explanation_text'] = raw_output
                except Exception as e:
                    results['explanation_text'] = f"Error parsing insights. Raw: {raw_output[:100]}..."

    return results

# ============================================================================
# ⚙️ Data Processing & Gradio Wrapper
# ============================================================================
async def process_request_async(message: str):
    try:
        if not message.strip():
            return "Error: Please enter a question", None, None, "Error: No question provided"

        results = await run_bi_pipeline_async(message)

        sql_query = results.get('sql_query', '')
        sql_query = sql_query.strip()
        if sql_query.startswith("```sql"):
            sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        elif sql_query.startswith("```"):
            sql_query = sql_query.replace("```", "").strip()

        query_results_str = results.get('query_results', '{}')
        try:
            query_results = json.loads(query_results_str) if isinstance(query_results_str, str) else query_results_str
        except:
            query_results = {'success': False, 'data': [], 'error': 'Failed to parse query results'}

        if not query_results.get('success', False):
            error_msg = query_results.get('error', 'Unknown error')
            sql_query = f"-- Error executing query\n{sql_query}\n\n-- Error: {error_msg}"
            return sql_query, None, None, f"Error executing query: {error_msg}"

        data_list = query_results.get('data', [])
        if not data_list:
            df = pd.DataFrame()
            return sql_query, df, None, "The query executed successfully but returned no data."

        df = pd.DataFrame(data_list)
        
        chart_spec = results.get('chart_spec', '')
        explanation_text = results.get('explanation_text', '')

        chart = None
        if chart_spec:
            try:
                chart_spec_clean = chart_spec.strip()
                if chart_spec_clean.startswith("```python"):
                    chart_spec_clean = chart_spec_clean.replace("```python", "").replace("```", "").strip()
                elif chart_spec_clean.startswith("```"):
                    chart_spec_clean = chart_spec_clean.replace("```", "").strip()

                namespace = {'alt': alt, 'pd': pd, 'df': df, 'data': df.to_dict(orient='records')}
                exec(chart_spec_clean, namespace)

                if 'chart' in namespace:
                    chart = namespace['chart']
            except Exception as e:
                print(f"Chart generation error: {str(e)}")
                import traceback
                traceback.print_exc()

        return sql_query, df, chart, explanation_text

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"Full error: {e}")
        import traceback
        traceback.print_exc()
        return error_msg, None, None, error_msg


def process_request(message: str):
    try:
        sql_query, df, chart, explanation = asyncio.run(
            process_request_async(message)
        )
        return sql_query, df, chart, explanation
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        return error_msg, None, None, error_msg

# ============================================================================
# 🎨 UI & Styling (จากโค้ดของเพื่อนคุณ)
# ============================================================================

bg_html = """

<style>
body, gradio-app {
    background-image: url('https://media.tenor.com/13MO7LUAShwAAAAM/fadding-cat.gif') !important;
    background-repeat: repeat !important;
    background-size: 150px !important;
    background-attachment: fixed !important;
}

.gradio-container {
    background-color: rgba(255, 255, 255, 0.7) !important;
    border-radius: 20px !important;
    box-shadow: 0 0 20px rgba(255, 182, 193, 0.5) !important;
    padding: 20px !important;
    margin-top: 20px !important;
}

:root, .dark, .light {
    --background-fill-primary: #ffffff !important;
    --background-fill-secondary: #fff0f5 !important;
    --block-background-fill: #ffffff !important;
    --input-background-fill: #ffffff !important;
    
    --body-text-color: #333333 !important;
    --body-text-color-subdued: #555555 !important;
    --block-label-text-color: #d14782 !important;
    
    --border-color-primary: #ffb6c1 !important;
    --block-border-color: #ffb6c1 !important;
    
    --table-border-color: #ffb6c1 !important;
    --table-odd-background-fill: #fff0f5 !important;
    --table-even-background-fill: #ffffff !important;
}

code, .cm-editor {
    background-color: #ffe4e1 !important;
    color: #d14782 !important;
}

h1, h2, h3, h4 { color: #d14782 !important; font-weight: bold !important; }
p, span, div, label { color: #333333 !important; }

.table-wrap {
    overflow: auto !important; 
    max-height: 500px !important; 
    border: 1px solid rgba(225, 126, 179) !important; 
    border-radius: 10px !important;
    background-color: white !important;
}

table {
    width: 100% !important;
    border-collapse: collapse !important;
    margin: 0 !important;
    table-layout: auto !important; 
}

.gradio-container table thead th,
.gradio-container table thead th * {
    background-color: rgba(255, 126, 179) !important;
    color: black !important;
    font-size: 14px !important;
    white-space: nowrap !important; 
}

td {
    background-color: white !important;
    color: #333333 !important;
    border-bottom: 1px solid rgb(255, 246, 239) !important;
    font-size: 13px !important;
    line-height: 1.2 !important;
}

tr:nth-child(even) td {
    background-color: rgb(235, 216, 219) !important; 
}

.table-wrap::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
.table-wrap::-webkit-scrollbar-thumb {
    background: #ffb6c1;
    border-radius: 10px;
}

button.primary {
    background: linear-gradient(to right, #ff9a9e 0%, #fecfef 100%) !important;
    border: none !important; color: #d14782 !important; font-weight: bold !important;
}
button.secondary {
    background: white !important; border: 2px solid #ffb6c1 !important; color: #ff69b4 !important; font-weight: bold !important;
}

.examples-container {
    transition: all 0.6s ease-in-out !important;
    overflow: hidden;
    max-height: 800px;
    opacity: 1;
}

.examples-hidden {
    max-height: 0 !important;
    opacity: 0 !important;
    margin: 0 !important;
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    pointer-events: none;
}

.examples-container {
    --table-row-background-hover: #ffe4e1 !important; 
    --background-fill-secondary-hover: #ffe4e1 !important; 
}

.examples-container button, 
.examples-container tbody tr,
.examples-container .gallery-item,
.examples-container div[role="button"] {
    transition: all 0.3s ease !important; 
}

.examples-container button:hover, 
.examples-container tbody tr:hover,
.examples-container .gallery-item:hover,
.examples-container div[role="button"]:hover {
    background: linear-gradient(to right, #ff9a9e 0%, #fecfef 100%) !important;
    background: linear-gradient(to right, #ff9a9e 0%, #fecfef 100%) !important;
    border-color: #ffb6c1 !important;
    color: white !important;
    box-shadow: 0 4px 12px rgba(255, 182, 193, 0.8) !important;
    transform: scale(1.03) !important;
    z-index: 10 !important;
}

button.primary {
    background: linear-gradient(to right, rgb(255 154 158) 0%, rgb(254 207 239) 100%) !important;
    border: none !important; 
    color: #d14782 !important; 
    font-weight: bold !important;
    transition: all 0.3s ease !important;
}

button.secondary {
    background: white !important; 
    border: 2px solid #ffb6c1 !important; 
    color: #ff69b4 !important; 
    font-weight: bold !important;
    transition: all 0.3s ease !important;
}

button.primary:hover {
    background: linear-gradient(to right, rgb(255 134 138) 0%, rgb(254 187 219) 100%) !important;
    transform: scale(1.03) !important;
    box-shadow: 0 6px 15px rgba(255, 126, 179, 0.6) !important;
}

button.secondary:hover {
    background-color: #fff0f5 !important;
    transform: scale(1.03) !important;
    box-shadow: 0 6px 15px rgba(255, 182, 193, 0.5) !important;
}



</style>
"""

gifs = [
    "https://media.tenor.com/Bi5t9IXWlEkAAAAM/funny-sad-emoji-getting-disintegrated-into-dust.gif",
    "https://media.tenor.com/AU6-SVlvHxIAAAAM/tatatattatatatatatattat.gif",
    "https://media1.tenor.com/m/JQPH-rsVS48AAAAd/jujutsu-kaisen-season-3.gif",
    "https://media.tenor.com/q-CmztRV07QAAAAM/cat-cat-meme.gif",
    "https://media.tenor.com/gik_H9PwwY0AAAAM/the-rock-sus-the-rock-meme.gif",
    "https://media.tenor.com/nAALWKg3aiUAAAAM/spider-man-meme-point.gif",
    "https://media1.giphy.com/media/v1.Y2lkPTc5MGI3NjExaWNwY205amtvOHowOTR5djBybWVjczBxdzI3amh6amh1aTk5YnV6biZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/DC34a8eBNqGGqgHnku/giphy.gif"
]

# ============================================================================
# Gradio UI
# ============================================================================

with gr.Blocks(
    title="Marketplace Stupidity Person (Safari Person Destroying Tools)"
    ) as demo:
    gr.HTML(bg_html)
    loading_screen = gr.HTML(value="", visible=False)

    with gr.Row(1):
        gr.Markdown("""
        # The Business Wizard of Intelligent on the Land of OOO 
        """)

    with gr.Row(9):
        with gr.Column(scale=2):
            with gr.Row(5):
                user_input = gr.Textbox(
                    label="Your Question",
                    placeholder="e.g., 'What are the top 10 products by price?'",
                    lines=3
                )

            # Examples
            with gr.Row(5):
                with gr.Column(elem_classes=["examples-container"]) as examples_container:
                    gr.Examples(
                        examples=[
                            ["What are the top 10 products by transfer price?"],
                            ["Show me the product categories and their average prices"],
                            ["List all products in the Bikes category"],
                            ["How many products are there in each category?"],
                            ["What is the most expensive product?"],
                            ["Compare the total Sales Amount and total Sales Amount Quota for each Product Category for the 'Actual' version."]
                        ],
                        inputs=user_input
                    )

            with gr.Row(2):
                submit_btn = gr.Button("Analyze Data", variant="primary")
                clear_btn = gr.Button("Clear")

            with gr.Row(12):
                with gr.Column():
                    gr.Markdown("### Data Table")
                    data_output = gr.DataFrame(
                        wrap=True
                    )            

    # Four output panels (จัดสเกลตามเพื่อน)
    
        with gr.Column(scale=3):
            
            with gr.Row(1):
                with gr.Column():
                    gr.Markdown("### Insights")
                    explanation_output = gr.Markdown(
                        value="*Waiting for input...*"
                    )
            
            with gr.Row(1):
                with gr.Column():
                    gr.Markdown("### Generated SQL")
                    sql_output = gr.Code(
                        label="SQL Query",
                        language="sql",
                        value="-- Waiting for input..."
                    )

            with gr.Row(4):
                with gr.Column():
                    gr.Markdown("### Visualization")
                    chart_output = gr.Plot(label="Chart")

            

    user_input.change(
        fn=None,
        inputs=[user_input],
        outputs=None,
        js="""
        function(text) {
            var el = document.querySelector('.examples-container');
            if (el) {
                if (text && text.trim().length > 0) {
                    el.classList.add('examples-hidden');
                } else {
                    el.classList.remove('examples-hidden');
                }
            }
        }
        """
    )
    
    def randomgifs():
        gif = random.choice(gifs)
        rangif = f"""
        <div style="position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                    background-color: rgba(255, 255, 255, 0.9); z-index: 9999;
                    display: flex; justify-content: center; align-items: center; flex-direction: column;">
            <img src="{gif}" style="width: 350px; border-radius: 15px; box-shadow: 0 10px 25px rgba(255, 182, 193, 0.8);">
            <h2 style="color: rgba(225, 71, 130, 1); margin-top: 20px; font-family: sans-serif; font-weight: bold;">
                Wait for the Analyze
            </h2>
        </div>
        """
        return gr.update(value=rangif, visible=True)

    # Button actions
    show_loading = submit_btn.click(
        fn=randomgifs,
        outputs=[loading_screen],
        queue=False
    )
    run_process = show_loading.then(
        fn=process_request,
        inputs=[user_input],
        outputs=[sql_output, data_output, chart_output, explanation_output]
    )
    run_process.then(
        fn=lambda: gr.update(value="", visible=False),
        outputs=[loading_screen],
        queue=False
    )

    clear_btn.click(
        fn=lambda: (
            "",
            "-- Waiting for input...",
            None,
            None,
            "*Waiting for input...*",
            gr.update(elem_classes=["examples-container"])
        ),
        inputs=None,
        outputs=[user_input, sql_output, data_output, chart_output, explanation_output, examples_container],
        js="""
        function() {
            var el = document.querySelector('.examples-container');
            if (el) {
                el.classList.remove('examples-hidden');
            }
            return [];
        }
        """
    )


if __name__ == "__main__":
    demo.launch()