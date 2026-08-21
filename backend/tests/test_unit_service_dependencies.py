import unittest

from pydantic import ValidationError

from app.schemas.service_dependency import ServiceDependencyCreate


class ServiceDependencySchemaTest(unittest.TestCase):
    def test_dependency_types_are_limited(self) -> None:
        dependency = ServiceDependencyCreate(source_target_id=1, destination_target_id=2, dependency_type="network")
        self.assertEqual(dependency.dependency_type, "network")
        with self.assertRaises(ValidationError):
            ServiceDependencyCreate(source_target_id=1, destination_target_id=2, dependency_type="shell")

    def test_target_ids_must_be_positive(self) -> None:
        with self.assertRaises(ValidationError):
            ServiceDependencyCreate(source_target_id=0, destination_target_id=2)


if __name__ == "__main__":
    unittest.main()