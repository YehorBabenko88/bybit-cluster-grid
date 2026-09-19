import asyncio, logging
log=logging.getLogger("agent_state")

class AgentControl:
    def __init__(self):
        self.enabled=True
        self.drain=False
        self.uninstall_requested=False
        self.generation=0

    def apply(self,command):
        action=(command or {}).get("action")
        generation=int((command or {}).get("generation",0))
        if generation <= self.generation:
            return
        self.generation=generation
        if action=="start":
            self.enabled=True; self.drain=False
        elif action=="stop":
            self.enabled=False; self.drain=True
        elif action=="restart":
            raise SystemExit("coordinator requested restart")
        elif action=="uninstall":
            # Worker only marks the request. A privileged local maintenance service performs removal.
            self.enabled=False; self.drain=True; self.uninstall_requested=True
        log.warning("agent command applied",extra={"event":"agent_command","component":str(action)})
