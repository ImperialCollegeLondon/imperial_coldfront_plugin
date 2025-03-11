def test_error_when_processing_job_exception():
    """Tests the ErrorWhenProcessingJob exception."""
    from imperial_coldfront_plugin.gpfs_client import ErrorWhenProcessingJob

    data = {"jobID": 42, "error": "Something bad happened."}

    try:
        raise ErrorWhenProcessingJob(data)
    except ErrorWhenProcessingJob as err:
        actual = err.args[0]

    assert actual == data
