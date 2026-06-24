import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useFormValidation } from "@/hooks/useFormValidation";

interface TestForm {
  name: string;
  email: string;
  age: number;
}

describe("useFormValidation", () => {
  const initialValues: TestForm = {
    name: "",
    email: "",
    age: 0,
  };

  it("initializes with provided initial values", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    expect(result.current.values).toEqual(initialValues);
    expect(result.current.errors).toEqual({});
    expect(result.current.isDirty).toBe(false);
    expect(result.current.isValid).toBe(true);
  });

  it("setValue updates a single field value", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    act(() => {
      result.current.setValue("name", "John");
    });

    expect(result.current.values.name).toBe("John");
    expect(result.current.isDirty).toBe(true);
  });

  it("setValues updates multiple fields", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    act(() => {
      result.current.setValues({ name: "John", email: "john@example.com" });
    });

    expect(result.current.values.name).toBe("John");
    expect(result.current.values.email).toBe("john@example.com");
    expect(result.current.isDirty).toBe(true);
  });

  it("setValues works with function updater", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    act(() => {
      result.current.setValues({ name: "John" });
    });

    act(() => {
      result.current.setValues((prev) => ({
        ...prev,
        email: `${prev.name.toLowerCase()}@example.com`,
      }));
    });

    expect(result.current.values.name).toBe("John");
    expect(result.current.values.email).toBe("john@example.com");
  });

  it("handleChange returns a function that updates the field", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    act(() => {
      result.current.handleChange("name")("Alice");
    });

    expect(result.current.values.name).toBe("Alice");
  });

  it("validate returns true when no validation schema", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    let isValid: boolean;
    act(() => {
      isValid = result.current.validate();
    });

    expect(isValid!).toBe(true);
    expect(result.current.isValid).toBe(true);
  });

  it("validateField validates a single field", () => {
    const validationSchema = {
      name: (value: string) => {
        if (!value) return "Name is required";
        return null;
      },
    };

    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues, validationSchema })
    );

    let error: string | null;
    act(() => {
      error = result.current.validateField("name");
    });

    expect(error).toBe("Name is required");
    expect(result.current.errors.name).toBe("Name is required");

    act(() => {
      result.current.setValue("name", "John");
    });

    act(() => {
      error = result.current.validateField("name");
    });

    expect(error).toBeNull();
    expect(result.current.errors.name).toBeUndefined();
  });

  it("validate validates all fields", () => {
    const validationSchema = {
      name: (value: string) => {
        if (!value) return "Name is required";
        return null;
      },
      email: (value: string) => {
        if (!value) return "Email is required";
        if (!value.includes("@")) return "Invalid email";
        return null;
      },
    };

    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues, validationSchema })
    );

    let isValid: boolean;
    act(() => {
      isValid = result.current.validate();
    });

    expect(isValid!).toBe(false);
    expect(result.current.errors.name).toBe("Name is required");
    expect(result.current.errors.email).toBe("Email is required");

    act(() => {
      result.current.setValues({ name: "John", email: "john@example.com" });
    });

    act(() => {
      isValid = result.current.validate();
    });

    expect(isValid!).toBe(true);
    expect(Object.keys(result.current.errors).length).toBe(0);
  });

  it("supports array of validation rules (returns first error)", () => {
    const validationSchema = {
      email: [
        (value: string) => (!value ? "Email is required" : null),
        (value: string) => (!value.includes("@") ? "Invalid email" : null),
      ],
    };

    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues, validationSchema })
    );

    act(() => {
      result.current.validateField("email");
    });

    expect(result.current.errors.email).toBe("Email is required");

    act(() => {
      result.current.setValue("email", "invalid");
    });

    act(() => {
      result.current.validateField("email");
    });

    expect(result.current.errors.email).toBe("Invalid email");
  });

  it("validateOnChange validates on field change", () => {
    const validationSchema = {
      name: (value: string) => {
        if (!value) return "Name is required";
        return null;
      },
    };

    const { result } = renderHook(() =>
      useFormValidation<TestForm>({
        initialValues,
        validationSchema,
        validateOnChange: true,
      })
    );

    act(() => {
      result.current.setValue("name", "");
    });

    expect(result.current.errors.name).toBe("Name is required");

    act(() => {
      result.current.setValue("name", "John");
    });

    expect(result.current.errors.name).toBeUndefined();
  });

  it("setError sets a specific field error", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    act(() => {
      result.current.setError("name", "Custom error");
    });

    expect(result.current.errors.name).toBe("Custom error");
    expect(result.current.isValid).toBe(false);

    act(() => {
      result.current.setError("name", null);
    });

    expect(result.current.errors.name).toBeUndefined();
    expect(result.current.isValid).toBe(true);
  });

  it("setErrors sets multiple errors", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    act(() => {
      result.current.setErrors({ name: "Error 1", email: "Error 2" });
    });

    expect(result.current.errors.name).toBe("Error 1");
    expect(result.current.errors.email).toBe("Error 2");
  });

  it("reset resets form to initial values", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    act(() => {
      result.current.setValues({ name: "John", email: "john@example.com" });
    });

    expect(result.current.isDirty).toBe(true);

    act(() => {
      result.current.reset();
    });

    expect(result.current.values).toEqual(initialValues);
    expect(result.current.isDirty).toBe(false);
    expect(result.current.errors).toEqual({});
  });

  it("resetErrors clears all errors", () => {
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues })
    );

    act(() => {
      result.current.setErrors({ name: "Error" });
    });

    expect(result.current.errors.name).toBe("Error");

    act(() => {
      result.current.resetErrors();
    });

    expect(result.current.errors).toEqual({});
    expect(result.current.isValid).toBe(true);
  });

  it("submit calls onSubmit when valid", async () => {
    const onSubmit = vi.fn();
    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues, onSubmit })
    );

    let success: boolean;
    await act(async () => {
      success = await result.current.submit();
    });

    expect(success!).toBe(true);
    expect(onSubmit).toHaveBeenCalledWith(initialValues);
  });

  it("submit does not call onSubmit when invalid", async () => {
    const validationSchema = {
      name: (value: string) => (!value ? "Required" : null),
    };
    const onSubmit = vi.fn();

    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues, validationSchema, onSubmit })
    );

    let success: boolean;
    await act(async () => {
      success = await result.current.submit();
    });

    expect(success!).toBe(false);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("validation rules receive form values as second argument", () => {
    const validationSchema = {
      age: (value: number, formValues: TestForm) => {
        if (formValues.name && value < 18) return "Must be 18 or older";
        return null;
      },
    };

    const { result } = renderHook(() =>
      useFormValidation<TestForm>({ initialValues, validationSchema })
    );

    act(() => {
      result.current.setValues({ name: "John", age: 15 });
    });

    act(() => {
      result.current.validateField("age");
    });

    expect(result.current.errors.age).toBe("Must be 18 or older");
  });
});
