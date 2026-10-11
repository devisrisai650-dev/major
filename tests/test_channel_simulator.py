import numpy as np

from channel_simulator import ChannelSimulator


def test_rain_attenuation_is_applied_once_to_snr():
    dry = ChannelSimulator(seed=123)
    rainy = ChannelSimulator(seed=123)

    dry.set_environment(rain_mm=0.0, flow_velocity_mps=1.0)
    rainy.set_environment(rain_mm=60.0, flow_velocity_mps=1.0)
    dry_measurements = dry.reset()
    rainy_measurements = rainy.reset()

    expected_loss_db = rainy_measurements["rain_attenuation_db"]
    measured_loss_db = dry_measurements["snr_db"] - rainy_measurements["snr_db"]

    assert expected_loss_db > 0.0
    assert np.allclose(measured_loss_db, expected_loss_db, atol=1e-10)
    assert np.isclose(
        rainy_measurements["doppler_hz"],
        dry_measurements["doppler_hz"],
    )


def test_environmental_rain_loss_is_zero_without_rain():
    simulator = ChannelSimulator(seed=7)
    simulator.set_environment(rain_mm=0.0)
    measurements = simulator.reset()

    assert measurements["rain_attenuation_db"] == 0.0


def test_relay_outage_removes_all_channel_actions_and_recovery_restores_them():
    simulator = ChannelSimulator(seed=11)
    simulator.set_environment(
        node_outage_probability=1.0,
        node_recovery_probability=0.0,
    )
    simulator.reset()
    simulator.advance()
    outage = simulator.measure()

    assert not outage["node_available"].any()
    assert outage["node_outage_count"] == simulator.n_channels
    assert not outage["available"].any()

    simulator.set_environment(
        node_outage_probability=0.0,
        node_recovery_probability=1.0,
    )
    simulator.advance()
    recovered = simulator.measure()

    assert recovered["node_available"].all()
    assert recovered["node_outage_count"] == 0
