from mainbrain.registry import get_agent, list_agents, list_sections, validate_registry


def test_exactly_50_unique_agents():
    agents = validate_registry()
    assert len(agents) == 50
    assert len({a.id for a in agents}) == 50
    assert [a.number for a in agents] == list(range(1, 51))


def test_all_agents_have_contracts_and_tools():
    for agent in list_agents():
        assert agent.description
        assert agent.prompt_template
        assert agent.contract.acceptance_criteria
        assert isinstance(agent.allowed_tools, list)
        assert agent.section


def test_sections_cover_ten_groups():
    sections = list_sections()
    assert len(sections) == 10
    assert "Vadība" in sections
    assert "Atmiņa un mācīšanās" in sections


def test_get_agent_case_insensitive():
    agent = get_agent("pythondeveloper")
    assert agent.id == "PythonDeveloper"
