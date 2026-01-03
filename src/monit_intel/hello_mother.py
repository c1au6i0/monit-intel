#!/usr/bin/env python
"""
Hello Mother: Interactive chat with the Monit-Intel agent.
Default mode is interactive chat. Use subcommands for other operations.
"""

import click
import requests
import json
from typing import Optional
from datetime import datetime
from tabulate import tabulate

API_URL = "http://localhost:8000"


@click.group(invoke_without_command=True)
@click.pass_context
def hello_mother(ctx):
    """
    Hello Mother: Interactive chat with the Monit-Intel agent.
    
    Start interactive chat mode by default. Use subcommands for specific operations:
    - hello_mother.py chat "query"     Send a single message
    - hello_mother.py history          View past conversations
    - hello_mother.py clear            Clear chat history
    - hello_mother.py actions          Manage system actions
    """
    ctx.ensure_object(dict)
    ctx.obj['api_url'] = API_URL
    
    # If no subcommand provided, start interactive mode
    if ctx.invoked_subcommand is None:
        _interactive_mode(ctx)


@hello_mother.command()
@click.argument('query')
@click.pass_context
def chat(ctx, query):
    """Chat with the agent using natural language."""
    try:
        response = requests.post(
            f"{ctx.obj['api_url']}/mother/chat",
            json={"query": query}
        )
        response.raise_for_status()
        
        data = response.json()
        
        click.echo()
        click.secho("🤖 Agent Response:", fg="cyan", bold=True)
        click.echo()
        click.echo(data["response"])
        click.echo()
        click.echo(f"Timestamp: {data['timestamp']}")
    
    except requests.exceptions.ConnectionError:
        click.secho(f"❌ Error: Cannot connect to {ctx.obj['api_url']}", fg="red")
        click.echo("Make sure the agent is running: pixi run python main.py --api 5 8000")
    except Exception as e:
        click.secho(f"❌ Error: {str(e)}", fg="red")


@hello_mother.command()
@click.option('--limit', default=10, help='Number of conversations to show')
@click.pass_context
def history(ctx, limit):
    """View conversation history."""
    try:
        response = requests.get(
            f"{ctx.obj['api_url']}/mother/history",
            params={"limit": limit}
        )
        response.raise_for_status()
        
        data = response.json()
        
        if not data["conversations"]:
            click.echo("📭 No conversation history yet.")
            return
        
        click.echo()
        click.secho(f"📋 Conversation History (last {limit}):", fg="cyan", bold=True)
        click.echo()
        
        for conv in data["conversations"]:
            click.secho(f"[{conv['timestamp']}]", fg="white")
            click.secho(f"👤 You: {conv['user_query'][:80]}...", fg="yellow")
            click.secho(f"🤖 Agent: {conv['agent_response'][:80]}...", fg="green")
            click.echo()
    
    except requests.exceptions.ConnectionError:
        click.secho(f"❌ Error: Cannot connect to {ctx.obj['api_url']}", fg="red")
    except Exception as e:
        click.secho(f"❌ Error: {str(e)}", fg="red")


@hello_mother.command()
@click.confirmation_option(prompt="Are you sure you want to clear all conversations?")
@click.pass_context
def clear(ctx):
    """Clear conversation history."""
    try:
        response = requests.delete(f"{ctx.obj['api_url']}/mother/clear")
        response.raise_for_status()
        
        click.secho("✓ Conversation history cleared.", fg="green")
    
    except requests.exceptions.ConnectionError:
        click.secho(f"❌ Error: Cannot connect to {ctx.obj['api_url']}", fg="red")
    except Exception as e:
        click.secho(f"❌ Error: {str(e)}", fg="red")


# ============================================================================
# ACTIONS: Suggest and Execute Safe Commands
# ============================================================================

@hello_mother.group()
def actions():
    """Manage safe system actions (restart services, check logs, etc.)."""
    pass


@actions.command()
@click.argument('action')
@click.argument('service')
@click.pass_context
def suggest(ctx, action, service):
    """Suggest an action without executing it."""
    try:
        response = requests.post(
            f"{ctx.obj['api_url']}/mother/actions/suggest",
            json={"action": action.lower(), "service": service}
        )
        response.raise_for_status()
        
        data = response.json()
        
        if not data.get("allowed"):
            click.secho(f"❌ Not allowed: {data.get('reason')}", fg="red")
            return
        
        click.echo()
        click.secho("✓ Suggested Action:", fg="green", bold=True)
        click.echo()
        click.secho(f"  Action: {data['action_type']}", fg="cyan")
        click.secho(f"  Service: {data['service']}", fg="cyan")
        click.secho(f"  Command: {data['command']}", fg="yellow")
        click.echo()
        click.secho(f"  Description: {data['description']}", fg="white")
        click.echo()
        click.secho("To execute: mother actions execute {action} {service} --approve", fg="white")
    
    except requests.exceptions.ConnectionError:
        click.secho(f"❌ Error: Cannot connect to {ctx.obj['api_url']}", fg="red")
    except Exception as e:
        click.secho(f"❌ Error: {str(e)}", fg="red")


@actions.command()
@click.argument('action')
@click.argument('service')
@click.option('--approve', is_flag=True, help='Approve execution (required)')
@click.pass_context
def execute(ctx, action, service, approve):
    """Execute a safe action with approval."""
    if not approve:
        click.secho("❌ Action requires --approve flag", fg="red")
        click.echo("Run: mother actions execute {action} {service} --approve")
        return
    
    # Double-check with user
    if not click.confirm(f"Execute '{action}' on '{service}'?"):
        click.echo("Cancelled.")
        return
    
    try:
        response = requests.post(
            f"{ctx.obj['api_url']}/mother/actions/execute",
            json={"action": action.lower(), "service": service, "approve": True}
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("success"):
            click.secho("✓ Action executed successfully!", fg="green", bold=True)
            click.echo()
            click.secho(f"Exit Code: {data.get('exit_code')}", fg="cyan")
            if data.get("output"):
                click.secho("Output:", fg="cyan", bold=True)
                click.echo(data["output"])
        else:
            click.secho(f"❌ Action failed: {data.get('reason')}", fg="red")
            if data.get("error"):
                click.echo(data["error"])
        
        click.echo()
        click.secho("All actions are logged for audit purposes.", fg="white")
    
    except requests.exceptions.ConnectionError:
        click.secho(f"❌ Error: Cannot connect to {ctx.obj['api_url']}", fg="red")
    except Exception as e:
        click.secho(f"❌ Error: {str(e)}", fg="red")


@actions.command()
@click.option('--limit', default=20, help='Number of audit entries to show')
@click.pass_context
def audit(ctx, limit):
    """View action audit log."""
    try:
        response = requests.get(
            f"{ctx.obj['api_url']}/mother/actions/audit",
            params={"limit": limit}
        )
        response.raise_for_status()
        
        data = response.json()
        
        if not data["audit_log"]:
            click.echo("📭 No action history yet.")
            return
        
        click.echo()
        click.secho(f"📋 Action Audit Log (last {limit}):", fg="cyan", bold=True)
        click.echo()
        
        table_data = []
        for log in data["audit_log"]:
            status = "✓" if log.get("exit_code") == 0 else "✗"
            table_data.append([
                log["timestamp"],
                log["action_type"],
                log["service"],
                status,
                log.get("error", "—")
            ])
        
        click.echo(tabulate(
            table_data,
            headers=["Timestamp", "Action", "Service", "Status", "Error"],
            tablefmt="grid"
        ))
    
    except ImportError:
        click.secho("⚠️  tabulate not installed. Install with: pip install tabulate", fg="yellow")
    except requests.exceptions.ConnectionError:
        click.secho(f"❌ Error: Cannot connect to {ctx.obj['api_url']}", fg="red")
    except Exception as e:
        click.secho(f"❌ Error: {str(e)}", fg="red")




def _interactive_mode(ctx):
    """Internal function for interactive chat (no Click decorators)."""
    api_url = ctx.obj.get('api_url', API_URL)
    
    click.secho("", fg="cyan")
    click.secho("🤖 Hello Mother - Interactive Chat Mode", fg="cyan", bold=True)
    click.secho("=" * 45, fg="cyan")
    click.secho("Type your question or 'help' for commands. 'quit' to exit.\n", fg="white")
    
    while True:
        try:
            user_input = click.prompt("You", type=str)
            
            if user_input.lower() == "quit":
                click.secho("\nGoodbye! 👋", fg="cyan")
                break
            elif user_input.lower() == "help":
                click.secho("""
┌─ Interactive Commands ─────────────────────┐
│ <any text>    - Chat with Mother          │
│ status        - Show service status       │
│ history       - View recent conversations │
│ clear         - Clear chat history        │
│ actions       - Manage system actions     │
│ quit          - Exit                      │
└────────────────────────────────────────────┘
                """, fg="white")
                continue
            elif user_input.lower() == "status":
                # Show service status
                try:
                    response = requests.get(f"{api_url}/status")
                    services = response.json()
                    
                    click.secho("\n📊 Service Status:", fg="cyan", bold=True)
                    for svc in services[:10]:  # Show first 10
                        status_str = "✓ HEALTHY" if svc['status'] == 0 else "✗ FAILED"
                        color = "green" if svc['status'] == 0 else "red"
                        click.secho(f"   {svc['name']:20} {status_str}", fg=color)
                    click.echo()
                except Exception as e:
                    click.secho(f"Error fetching status: {e}", fg="red")
                continue
            elif user_input.lower() == "history":
                # Show history
                try:
                    response = requests.get(f"{api_url}/mother/history?limit=5")
                    data = response.json()
                    
                    if data["conversations"]:
                        click.secho("\n📋 Recent Conversations:", fg="cyan", bold=True)
                        for conv in data["conversations"]:
                            click.secho(f"\n  [{conv['timestamp']}]", fg="white")
                            click.secho(f"  You: {conv['user_query'][:60]}...", fg="yellow")
                            click.secho(f"  Mother: {conv['agent_response'][:60]}...", fg="green")
                        click.echo()
                    else:
                        click.echo("No conversation history yet.\n")
                except Exception as e:
                    click.secho(f"Error fetching history: {e}", fg="red")
                continue
            elif user_input.lower() == "clear":
                if click.confirm("Clear all conversations?"):
                    try:
                        requests.delete(f"{api_url}/mother/clear")
                        click.secho("✓ History cleared.\n", fg="green")
                    except Exception as e:
                        click.secho(f"Error: {e}", fg="red")
                continue
            elif user_input.lower().startswith("actions"):
                click.secho("\nUse: hello_mother.py actions <suggest|execute|audit> ...\n", fg="white")
                continue
            
            # Chat with agent
            if user_input.strip():
                response = requests.post(
                    f"{api_url}/mother/chat",
                    json={"query": user_input},
                    timeout=30
                )
                response.raise_for_status()
                
                data = response.json()
                click.secho(f"\nMother: {data['response']}\n", fg="green")
        
        except KeyboardInterrupt:
            click.secho("\n\nGoodbye! 👋", fg="cyan")
            break
        except requests.exceptions.ConnectionError:
            click.secho(f"\n❌ Cannot connect to agent at {api_url}", fg="red")
            click.secho("Start it with: pixi run python main.py --api 5 8000\n", fg="white")
            break
        except Exception as e:
            click.secho(f"❌ Error: {str(e)}", fg="red")


@hello_mother.command()
@click.pass_context
def interactive(ctx):
    """Start interactive chat mode (type 'help' for commands, 'quit' to exit)."""
    _interactive_mode(ctx)


def main():
    """Main entry point for hello_mother CLI."""
    hello_mother(obj={})


if __name__ == "__main__":
    main()
