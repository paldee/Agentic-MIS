import time
import pandas as pd
import gradio as gr
import asyncio
import os
import pandas as pd
import altair as alt
from dotenv import load_dotenv
from google.genai import types
import json

# Import root agent runner
from bi_agent.tools import execute_sql_and_format 
from bi_agent.tools import get_database_schema
from bi_agent.agent import text_to_sql_runner, analysis_runner
# Load environment variables from bi_agent/.env
load_dotenv(dotenv_path='bi_agent/.env')


async def run_bi_pipeline_async(user_question: str):
    results = {}
    start_step1 = time.time()
    print("🤖 1. Generating SQL...")
    session_sql = await text_to_sql_runner.session_service.create_session(
        user_id='user', 
        app_name='text_to_sql'
    )

    schema_context = get_database_schema()
    enhanced_prompt = f"""
Here is the Database Schema you must use:
{schema_context}

User Question: {user_question}
"""

    content_sql = types.Content(role='user', parts=[types.Part(text=enhanced_prompt)])
    events_sql = text_to_sql_runner.run_async(
        user_id='user', 
        session_id=session_sql.id, 
        new_message=content_sql
    )
    sql_query = ""
    async for event in events_sql:
        if event.actions and event.actions.state_delta:
            if 'sql_query' in event.actions.state_delta:
                sql_query = event.actions.state_delta['sql_query']

    results['sql_query'] = sql_query
    end_step1 = time.time()
    print(f"⏱️ เวลาที่ AI ใช้เขียน SQL: {end_step1 - start_step1:.2f} วินาที")
# --------------------------------------------------------------------
    start_step2 = time.time()
    print("⚡️ 2. Executing SQL (Python)...")
    if sql_query:
        clean_sql = sql_query.replace("```sql", "").replace("```", "").strip()
        try:
            query_results_json = execute_sql_and_format(clean_sql)
            results['query_results'] = query_results_json
        except Exception as e:
            results['query_results'] = json.dumps({"success": False, "error": str(e)})
            return results # Stop if execution fails
    else:
        return results
    end_step2 = time.time()
    print(f"⏱️ เวลาที่ Database ใช้ดึงข้อมูล: {end_step2 - start_step2:.2f} วินาที")
    try:
        data_dict = json.loads(query_results_json)
        if data_dict.get('success') and data_dict.get('data'):
            df_temp = pd.DataFrame(data_dict['data'])

            fast_chart_spec, fast_explanation = get_heuristic_analysis(df_temp)

            if fast_chart_spec and fast_explanation:
                print("🚀 FAST TRACK: Using Python to generate chart (Skipping AI Analysis!)")
                results['chart_spec'] = fast_chart_spec
                results['explanation_text'] = fast_explanation

                return results 
    except Exception as e:
        print(f"Heuristic bypass failed: {e}")
# ------------------------------------------------------------------------
    session_viz = await analysis_runner.session_service.create_session(
        user_id='user', 
        app_name='analysis'
    )
    analysis_prompt = f"""
Analyze the following data results:
{results['query_results']}

Remember to return JSON with 'chart_spec' and 'explanation'.
"""
    content_viz = types.Content(role='user', parts=[types.Part(text=analysis_prompt)])

    # Run Agent 2: Analyze Data (Viz + Explain combined)
    events_viz = analysis_runner.run_async(
        user_id='user', 
        session_id=session_viz.id, 
        new_message=content_viz
    )

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
                        print(f"⚠️ Warning: Could not find JSON brackets in: {raw_output}")
                        results['explanation_text'] = raw_output

                except Exception as e:
                    print(f"❌ JSON Parse Error: {e}")
                    print(f"Raw Output: {raw_output}")
                    results['explanation_text'] = f"Error parsing insights. Raw: {raw_output[:100]}..."

    return results

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
            
            chart_spec = f"""chart = alt.Chart(df).mark_bar().encode(x=alt.X('{val}:Q'),y=alt.Y('{dim}:N', sort='-x', title=None),tooltip=['{dim}', '{val}']).properties(title='{val} by {dim}').interactive()"""
            top_row = df.sort_values(by=val, ascending=False).iloc[0]
            val_formatted = f"{top_row[val]:,.2f}" if isinstance(top_row[val], float) else f"{top_row[val]}"
            explanation = f"The highest `{dim}` is **{top_row[dim]}** with a total `{val}` of {val_formatted}."
            
            return chart_spec, explanation

    if len(df) == 1 and len(cols) > 1:
        if all(pd.api.types.is_numeric_dtype(df[c]) for c in cols):
            chart_spec = """df_melted = df.melt(var_name='Metric', value_name='Value')
base = alt.Chart(df_melted).encode(x='Value:Q', y=alt.Y('Metric:N', title=None, sort='-x'))
bars = base.mark_bar()
text = base.mark_text(align='left', dx=5).encode(text='Value:Q')
chart = (bars + text).properties(title='Key Metrics Overview').interactive()
"""
            explanation = "⚡️ **Fast Analysis:** The chart displays the key metrics from your query for direct comparison."
            return chart_spec, explanation
    return None, None

async def process_request_async(message: str):
    """
    Process user request through the BI pipeline using root_runner.

    The root_agent handles the complete pipeline:
    1. Text-to-SQL Agent → Generates SQL from question
    2. SQL Executor Agent → Executes SQL against database
    3. Data Formatter Agent → Formats results
    4. Insight Pipeline → Visualization + Explanation

    Args:
        message: User's natural language question

    Returns:
        Tuple of (sql_query, df, chart, explanation_text)
    """
    try:
        # Validate input
        if not message.strip():
            return "Error: Please enter a question", None, None, "Error: No question provided"

        # Run the complete BI pipeline
        results = await run_bi_pipeline_async(message)

        # Extract SQL query
        sql_query = results.get('sql_query', '')

        # Clean up SQL query (remove markdown if present)
        sql_query = sql_query.strip()
        if sql_query.startswith("```sql"):
            sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
        elif sql_query.startswith("```"):
            sql_query = sql_query.replace("```", "").strip()

        # Extract query results
        query_results_str = results.get('query_results', '{}')
        try:
            query_results = json.loads(query_results_str) if isinstance(query_results_str, str) else query_results_str
        except:
            query_results = {'success': False, 'data': [], 'error': 'Failed to parse query results'}

        # Check if query execution was successful
        if not query_results.get('success', False):
            error_msg = query_results.get('error', 'Unknown error')
            sql_query = f"-- Error executing query\n{sql_query}\n\n-- Error: {error_msg}"
            return sql_query, None, None, f"Error executing query: {error_msg}"

        # Convert query results to DataFrame
        data_list = query_results.get('data', [])
        if not data_list:
            df = pd.DataFrame()
            return sql_query, df, None, "The query executed successfully but returned no data."

        df = pd.DataFrame(data_list)

        # Extract chart specification and explanation
        chart_spec = results.get('chart_spec', '')
        explanation_text = results.get('explanation_text', '')

        # Execute chart specification
        chart = None
        if chart_spec:
            try:
                chart_spec_clean = chart_spec.strip()
                if chart_spec_clean.startswith("```python"):
                    chart_spec_clean = chart_spec_clean.replace("```python", "").replace("```", "").strip()
                elif chart_spec_clean.startswith("```"):
                    chart_spec_clean = chart_spec_clean.replace("```", "").strip()

                # Create namespace and execute chart code
                namespace = {
                    'alt': alt,
                    'pd': pd,
                    'df': df,
                    'data': df.to_dict(orient='records')
                }

                exec(chart_spec_clean, namespace)

                if 'chart' in namespace:
                    chart = namespace['chart']
            except Exception as e:
                print(f"Chart generation error: {str(e)}")
                import traceback
                traceback.print_exc()

        # Return all four outputs
        return sql_query, df, chart, explanation_text

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"Full error: {e}")
        import traceback
        traceback.print_exc()
        return error_msg, None, None, error_msg


def process_request(message: str):
    """
    Synchronous wrapper for Gradio.

    Database credentials are read from environment variables in bi_agent/.env
    """
    try:
        sql_query, df, chart, explanation = asyncio.run(
            process_request_async(message)
        )
        return sql_query, df, chart, explanation
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        return error_msg, None, None, error_msg


# ============================================================================
# Gradio UI
# ============================================================================

with gr.Blocks(title="Business Intelligence Agent") as demo:
    gr.Markdown("""
    # Business Intelligence Agent (Google ADK)

    This demo uses **Google ADK's root_agent SequentialAgent**:

    1. **Text-to-SQL Agent** → Generates SQL from natural language
    2. **SQL Executor Agent** → Executes SQL against database
    3. **Data Formatter Agent** → Prepares results for visualization
    4. **Insight Pipeline** (**SequentialAgent**) → Visualization Agent → Explanation Agent

    Database credentials are configured in `bi_agent/.env`

    Enter your question below and click "Analyze Data".
    """)

    with gr.Row():
        user_input = gr.Textbox(
            label="Your Question",
            placeholder="e.g., 'What are the top 10 products by price?'",
            lines=3
        )

    with gr.Row():
        submit_btn = gr.Button("Analyze Data", variant="primary")
        clear_btn = gr.Button("Clear")

    gr.Markdown("## Results")

    # Four output panels
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Generated SQL")
            sql_output = gr.Code(
                label="SQL Query",
                language="sql",
                value="-- Waiting for input..."
            )

        with gr.Column(scale=1):
            gr.Markdown("### Query Results")
            data_output = gr.DataFrame(
                label="Data Table",
                wrap=True
            )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### Visualization")
            chart_output = gr.Plot(label="Chart")

        with gr.Column(scale=1):
            gr.Markdown("### Insights")
            explanation_output = gr.Markdown(
                value="*Waiting for input...*"
            )

    # Examples
    gr.Examples(
        examples=[
            ["What are the top 10 products by transfer price?"],
            ["Show me the product categories and their average prices"],
            ["List all products in the Bikes category"],
            ["How many products are there in each category?"],
            ["What is the most expensive product?"],
        ],
        inputs=user_input
    )

    # Button actions
    submit_btn.click(
        fn=process_request,
        inputs=[user_input],
        outputs=[sql_output, data_output, chart_output, explanation_output]
    )

    clear_btn.click(
        fn=lambda: (
            "",
            "-- Waiting for input...",
            None,
            None,
            "*Waiting for input...*"
        ),
        inputs=None,
        outputs=[user_input, sql_output, data_output, chart_output, explanation_output]
    )


if __name__ == "__main__":
    demo.launch()
