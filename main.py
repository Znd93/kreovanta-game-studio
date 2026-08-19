from agents.game_director import GameDirectorAgent
from agents.producer import ProducerAgent
from agents.researcher import ResearcherAgent
from core.message_bus import MessageBus
from core.workflow import run_discovery_workflow


FOUNDER_REQUEST = "Find a simple Roblox game opportunity."


def _print_agent_outputs(bus: MessageBus) -> None:
    for message in bus.history():
        if message.sender == "producer":
            print("\n=== PRODUCER ===")
            print(message.payload.get("producer_message", message.payload))
        elif message.sender == "researcher":
            print("\n=== RESEARCHER ===")
            print(message.payload.get("research_findings", message.payload))
        elif message.sender == "game_director":
            print("\n=== GAME DIRECTOR ===")
            print(message.payload.get("recommendation", message.payload))


def _handle_founder_decision(founder_decision: str) -> None:
    print("\n=== FOUNDER DECISION ===")

    if founder_decision == "APPROVE":
        print("APPROVED")
        print("Game plan may continue to the next development stage.")
    elif founder_decision == "CHANGE":
        print("CHANGES REQUESTED")
        print("The plan must return to Game Director before development.")
    elif founder_decision == "REJECT":
        print("REJECTED")
        print("Development is blocked.")
    else:
        print("INVALID DECISION")
        print("Development remains blocked.")


def main() -> None:
    bus = MessageBus()
    final_message = run_discovery_workflow(
        founder_request=FOUNDER_REQUEST,
        producer=ProducerAgent(),
        researcher=ResearcherAgent(),
        game_director=GameDirectorAgent(),
        bus=bus,
    )

    _print_agent_outputs(bus)

    print("\n=== STATUS ===")
    if final_message.requires_approval:
        print("WAITING FOR FOUNDER APPROVAL")
    else:
        print(final_message.status.value.upper())

    founder_decision = input(
        "\nFounder decision [APPROVE / CHANGE / REJECT]: "
    ).strip().upper()
    _handle_founder_decision(founder_decision)


if __name__ == "__main__":
    main()
