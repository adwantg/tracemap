from rich.console import Console
import socket
import dns.resolver

def check_dns_consistency(host: str, console: Console) -> None:
    """
    Check DNS resolution across multiple resolvers to detect inconsistencies.
    
    Args:
        host: Hostname to resolve
        console: Rich console for output
    """
    resolvers = {
        "System": None,
        "Cloudflare (1.1.1.1)": "1.1.1.1",
        "Google (8.8.8.8)": "8.8.8.8",
        "Quad9 (9.9.9.9)": "9.9.9.9"
    }
    
    results = {}
    
    for name, ip in resolvers.items():
        try:
            if ip:
                res = dns.resolver.Resolver()
                res.nameservers = [ip]
                # Default timeout
                res.lifetime = 2.0
                answers = res.resolve(host, 'A')
                ips = sorted([str(r) for r in answers])
            else:
                # System resolver
                # Use socket.getaddrinfo to get all IPs
                answers = socket.getaddrinfo(host, None, socket.AF_INET)
                ips = sorted(list(set([a[4][0] for a in answers])))
                
            results[name] = ips
            
        except Exception as e:
            results[name] = f"Error: {e}"

    # Display results
    from rich.table import Table
    t = Table(show_header=True, title=f"DNS Check: {host}")
    t.add_column("Resolver", style="cyan")
    t.add_column("Result IP(s)")
    t.add_column("Match System", justify="center")
    
    system_ips = results.get("System")
    if isinstance(system_ips, list):
        base_set = set(system_ips)
    else:
        base_set = set()

    for name, res in results.items():
        if isinstance(res, list):
            res_str = ", ".join(res)
            is_match = set(res) == base_set if base_set else False
            match_icon = "[green]✓[/green]" if is_match or name == "System" else "[yellow]≠[/yellow]"
        else:
            res_str = f"[red]{res}[/red]"
            match_icon = "[red]✗[/red]"
            
        t.add_row(name, res_str, match_icon)
        
    console.print(t)
