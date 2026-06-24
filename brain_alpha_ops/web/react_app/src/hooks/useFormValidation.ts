import { useState, useCallback, useMemo, useRef, useEffect } from "react";

export type ValidationRule<T> = (value: T, formValues: T) => string | null;

export type ValidationSchema<T extends Record<string, any>> = {
  [K in keyof T]?: ValidationRule<T[K]> | Array<ValidationRule<T[K]>>;
};

export type FormErrors<T extends Record<string, any>> = {
  [K in keyof T]?: string;
};

export interface UseFormValidationOptions<T extends Record<string, any>> {
  initialValues: T;
  validationSchema?: ValidationSchema<T>;
  validateOnChange?: boolean;
  onSubmit?: (values: T) => void | Promise<void>;
}

export interface UseFormValidationResult<T extends Record<string, any>> {
  values: T;
  errors: FormErrors<T>;
  isValid: boolean;
  isDirty: boolean;
  touched: Record<keyof T, boolean>;
  setValue: <K extends keyof T>(key: K, value: T[K]) => void;
  setValues: (values: Partial<T> | ((prev: T) => Partial<T>)) => void;
  setError: <K extends keyof T>(key: K, error: string | null) => void;
  setErrors: (errors: FormErrors<T>) => void;
  handleChange: <K extends keyof T>(key: K) => (value: T[K]) => void;
  validateField: <K extends keyof T>(key: K) => string | null;
  validate: () => boolean;
  reset: () => void;
  resetErrors: () => void;
  submit: () => Promise<boolean>;
}

export function useFormValidation<T extends Record<string, any>>(
  options: UseFormValidationOptions<T>
): UseFormValidationResult<T> {
  const { initialValues, validationSchema, validateOnChange = false, onSubmit } = options;

  const [values, setValuesState] = useState<T>(initialValues);
  const [errors, setErrorsState] = useState<FormErrors<T>>({});
  const [touched, setTouchedState] = useState<Record<keyof T, boolean>>({} as Record<keyof T, boolean>);
  const [initialValuesState] = useState<T>(initialValues);

  const valuesRef = useRef<T>(values);

  useEffect(() => {
    valuesRef.current = values;
  }, [values]);

  const isDirty = useMemo(() => {
    return JSON.stringify(values) !== JSON.stringify(initialValuesState);
  }, [values, initialValuesState]);

  const isValid = useMemo(() => {
    return Object.keys(errors).length === 0;
  }, [errors]);

  const runFieldValidation = useCallback(
    <K extends keyof T>(key: K, currentValues: T): string | null => {
      if (!validationSchema) return null;

      const rules = validationSchema[key];
      if (!rules) return null;

      const ruleList = Array.isArray(rules) ? rules : [rules];

      for (const rule of ruleList) {
        const error = rule(currentValues[key], currentValues);
        if (error) return error;
      }

      return null;
    },
    [validationSchema]
  );

  const validateField = useCallback(
    <K extends keyof T>(key: K): string | null => {
      const currentValues = valuesRef.current;
      const error = runFieldValidation(key, currentValues);
      setErrorsState((prev) => {
        const next = { ...prev };
        if (error) {
          next[key] = error;
        } else {
          delete next[key];
        }
        return next;
      });
      return error;
    },
    [runFieldValidation]
  );

  const validate = useCallback((): boolean => {
    if (!validationSchema) return true;

    const currentValues = valuesRef.current;
    const newErrors: FormErrors<T> = {};
    let hasError = false;

    for (const key of Object.keys(validationSchema) as Array<keyof T>) {
      const error = runFieldValidation(key, currentValues);
      if (error) {
        newErrors[key] = error;
        hasError = true;
      }
    }

    setErrorsState(newErrors);
    return !hasError;
  }, [validationSchema, runFieldValidation]);

  const setValue = useCallback(
    <K extends keyof T>(key: K, value: T[K]) => {
      setValuesState((prev) => {
        const next = { ...prev, [key]: value };
        valuesRef.current = next;

        if (validateOnChange && validationSchema?.[key]) {
          const error = runFieldValidation(key, next);
          setErrorsState((prevErrors) => {
            const nextErrors = { ...prevErrors };
            if (error) {
              nextErrors[key] = error;
            } else {
              delete nextErrors[key];
            }
            return nextErrors;
          });
        }

        return next;
      });

      setTouchedState((prev) => ({ ...prev, [key]: true }));
    },
    [validateOnChange, validationSchema, runFieldValidation]
  );

  const setValues = useCallback(
    (updates: Partial<T> | ((prev: T) => Partial<T>)) => {
      setValuesState((prev) => {
        const partial = typeof updates === "function" ? updates(prev) : updates;
        const next = { ...prev, ...partial };
        valuesRef.current = next;

        if (validateOnChange && validationSchema) {
          const newErrors: FormErrors<T> = {};
          for (const key of Object.keys(partial) as Array<keyof T>) {
            if (validationSchema[key]) {
              const error = runFieldValidation(key, next);
              if (error) {
                newErrors[key] = error;
              }
            }
          }
          if (Object.keys(newErrors).length > 0) {
            setErrorsState((prevErrors) => ({ ...prevErrors, ...newErrors }));
          }
        }

        return next;
      });

      setTouchedState((prev) => {
        const partial = typeof updates === "function" ? {} : updates;
        const next = { ...prev };
        for (const key of Object.keys(partial) as Array<keyof T>) {
          next[key] = true;
        }
        return next;
      });
    },
    [validateOnChange, validationSchema, runFieldValidation]
  );

  const setError = useCallback(<K extends keyof T>(key: K, error: string | null) => {
    setErrorsState((prev) => {
      const next = { ...prev };
      if (error) {
        next[key] = error;
      } else {
        delete next[key];
      }
      return next;
    });
  }, []);

  const setErrors = useCallback((newErrors: FormErrors<T>) => {
    setErrorsState(newErrors);
  }, []);

  const handleChange = useCallback(
    <K extends keyof T>(key: K) => {
      return (value: T[K]) => {
        setValue(key, value);
      };
    },
    [setValue]
  );

  const reset = useCallback(() => {
    setValuesState(initialValuesState);
    valuesRef.current = initialValuesState;
    setErrorsState({});
    setTouchedState({} as Record<keyof T, boolean>);
  }, [initialValuesState]);

  const resetErrors = useCallback(() => {
    setErrorsState({});
  }, []);

  const submit = useCallback(async (): Promise<boolean> => {
    const isValid = validate();
    if (!isValid) return false;

    if (onSubmit) {
      await onSubmit(valuesRef.current);
    }

    return true;
  }, [validate, onSubmit]);

  return {
    values,
    errors,
    isValid,
    isDirty,
    touched,
    setValue,
    setValues,
    setError,
    setErrors,
    handleChange,
    validateField,
    validate,
    reset,
    resetErrors,
    submit,
  };
}
